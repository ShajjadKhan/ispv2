"""
MikroTik RouterOS API Client for CyberNet v2.
Handles live connectivity checks, system resource metrics, interface states, and latency.
"""

import time
import re
import logging
from typing import List, Dict, Any, Optional, Union
from concurrent.futures import ThreadPoolExecutor
import routeros_api

logger = logging.getLogger("mikrotik_v2")

def format_bytes(b: Union[int, str, float]) -> str:
    """Formats raw byte counts into human-readable B, KB, MB, or GB."""
    try:
        n = float(b or 0)
    except Exception:
        return "0 B"
    if n < 1024:
        return f"{int(n)} B"
    elif n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    elif n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    else:
        return f"{n / (1024 * 1024 * 1024):.2f} GB"

def normalize_rate_limit(rate: Optional[str]) -> Optional[str]:
    """
    Normalizes rate limit string for MikroTik /queue/simple:
    - None, "", "0", "0M/0M", "0/0", "unlimited", "none" -> None (meaning unlimited)
    - "20" or "20M" or "20 Mbps" -> "20M/20M"
    - "10M/20M" -> "10M/20M"
    """
    if not rate:
        return None
    r = str(rate).strip().lower()
    if r in ("0", "0m", "0k", "0/0", "0m/0m", "unlimited", "none", "", "null"):
        return None
    if "/" in r:
        parts = r.split("/")
        p1 = parts[0].strip()
        p2 = parts[1].strip()
        if p1.isdigit():
            p1 = f"{p1}M"
        if p2.isdigit():
            p2 = f"{p2}M"
        return f"{p1.upper()}/{p2.upper()}"
    val = re.sub(r"[^\d.]", "", r)
    if val:
        try:
            num = int(float(val))
            if num <= 0:
                return None
            return f"{num}M/{num}M"
        except Exception:
            pass
    return str(rate).strip()

def is_randomized_mac(mac: Optional[str]) -> bool:
    """
    Checks if a MAC address is locally administered (randomized / private MAC).
    Under IEEE 802 MAC standard, if the second hex digit of the first octet
    is 2, 6, A, or E (case-insensitive), it is a locally administered (randomized) MAC.
    """
    if not mac:
        return False
    clean = re.sub(r'[^0-9A-Fa-f]', '', str(mac).strip())
    if len(clean) < 2:
        return False
    try:
        first_byte = int(clean[:2], 16)
        return bool(first_byte & 0x02)
    except ValueError:
        return False


def parse_routeros_duration(val: Optional[str]) -> Optional[int]:
    """
    Parses RouterOS duration string (e.g. '1h55m3s', '4m5s', '8s', '2d1h', '3w') into total seconds.
    Returns None if cannot parse or 'never' / '—'.
    """
    if not val or val in ('never', '—', ''):
        return None
    val = str(val).strip().lower()
    matches = re.findall(r'(\d+)([wdhms])', val)
    if not matches:
        try:
            return int(val)
        except ValueError:
            return None
    multipliers = {'w': 604800, 'd': 86400, 'h': 3600, 'm': 60, 's': 1}
    return sum(int(amount) * multipliers.get(unit, 0) for amount, unit in matches)


def clean_device_friendly_name(stored_name: Optional[str], dhcp_host_name: Optional[str] = None) -> str:
    """
    Cleans up User-Agent strings or unhelpful device names to provide a clean, human-readable label.
    """
    if dhcp_host_name and dhcp_host_name.strip() and dhcp_host_name not in ("*", "—", "unknown"):
        clean_dhcp = dhcp_host_name.strip().replace("-", " ")
        if not stored_name or "Mozilla" in stored_name or "AppleWebKit" in stored_name:
            return clean_dhcp

    if not stored_name or not stored_name.strip():
        return dhcp_host_name or "Client Device"

    name = stored_name.strip()
    if "Mozilla" in name or "AppleWebKit" in name:
        if "iPhone" in name:
            return "Apple iPhone"
        if "iPad" in name:
            return "Apple iPad"
        if "Android" in name:
            return "Android Device"
        if "Macintosh" in name or "Mac OS" in name:
            return "Apple Mac"
        if "Windows" in name:
            return "Windows PC"
        if "Linux" in name:
            return "Linux Device"
        return "Mobile Device"

    if len(name) > 28:
        return name[:26] + "…"
    return name


class RouterClient:
    def __init__(
        self,
        host: str = "10.20.30.1",
        username: str = "admin",
        password: str = "admin",
        port: int = 8728,
        use_ssl: bool = False,
        router_id: Optional[int] = None
    ):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.use_ssl = use_ssl
        self.router_id = router_id
        self._telemetry_cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._telemetry_cache_time: float = 0.0
        self._live_status_cache: Optional[Dict[str, Any]] = None
        self._live_status_cache_time: float = 0.0
        self._online_macs_cache: Optional[List[str]] = None
        self._online_macs_cache_time: float = 0.0

    def refresh_from_db(self):
        """Dynamically reloads router connection parameters from database if available."""
        try:
            import database
            if self.router_id is not None:
                r = database.get_router_by_id(self.router_id)
                if r:
                    self.host = r.get("host") or self.host
                    self.username = r.get("username") or self.username
                    self.password = r.get("password") or self.password
                    self.port = r.get("port") or self.port
                    self.use_ssl = (self.port == 8729 or bool(r.get("use_ssl", False)))
                return

            routers = database.get_all_routers(active_only=True)
            if routers:
                default_r = next((r for r in routers if r.get("is_default")), routers[0])
                if default_r:
                    self.host = default_r.get("host") or self.host
                    self.username = default_r.get("username") or self.username
                    self.password = default_r.get("password") or self.password
                    self.port = default_r.get("port") or self.port
                    self.use_ssl = (self.port == 8729 or bool(default_r.get("use_ssl", False)))
        except Exception:
            pass

    def get_live_status(self, max_cache_age_sec: float = 5.0) -> Dict[str, Any]:
        """
        Connects to MikroTik and fetches live status, resource metrics, and interfaces.
        Returns a structured dictionary with success state, latency, and hardware telemetry.
        Cached in memory for max_cache_age_sec to minimize socket stalls.
        """
        now = time.time()
        if self._live_status_cache is not None and (now - self._live_status_cache_time) < max_cache_age_sec:
            if self._live_status_cache.get("connected"):
                return self._live_status_cache

        self.refresh_from_db()
        start_time = time.time()
        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()
            latency_ms = round((time.time() - start_time) * 1000, 1)

            # 1. System Resource
            res_list = api.get_resource('/system/resource').get()
            res = res_list[0] if res_list else {}

            # 2. System Identity
            ident_list = api.get_resource('/system/identity').get()
            identity = ident_list[0].get('name', 'MikroTik') if ident_list else 'MikroTik'

            # 3. RouterBoard Hardware Details
            try:
                rb_list = api.get_resource('/system/routerboard').get()
                rb = rb_list[0] if rb_list else {}
            except Exception:
                rb = {}

            # 4. Interfaces & Hardware Physical Ports
            try:
                ifaces_raw = api.get_resource('/interface').get()
            except Exception as e:
                logger.warning(f"Failed to fetch /interface from {self.host}: {e}")
                ifaces_raw = []

            eth_map = {}
            try:
                eth_raw = api.get_resource('/interface/ethernet').get()
                for e in eth_raw:
                    eth_map[e.get("name")] = e
            except Exception as e:
                logger.debug(f"Could not fetch /interface/ethernet from {self.host}: {e}")

            interfaces = []
            for i in ifaces_raw:
                name = i.get("name", "")
                name_lower = name.lower()
                itype = i.get("type", "")

                is_sfp = name_lower.startswith("sfp") or "sfp" in itype.lower() or (name in eth_map and "sfp" in eth_map[name].get("default-name", "").lower())
                is_eth = (name in eth_map) or (itype == "ether") or name_lower.startswith("ether")
                is_wlan = name_lower.startswith("wlan") or "wlan" in itype.lower() or "wifi" in itype.lower()
                is_loopback = itype == "loopback" or name_lower == "lo"

                if is_sfp:
                    media_type = "sfp"
                    is_physical = True
                elif is_eth:
                    media_type = "ether"
                    is_physical = True
                elif is_wlan:
                    media_type = "wireless"
                    is_physical = True
                elif is_loopback:
                    media_type = "loopback"
                    is_physical = False
                else:
                    media_type = itype
                    is_physical = False

                eth_info = eth_map.get(name, {})
                interfaces.append({
                    "name": name,
                    "default_name": i.get("default-name") or eth_info.get("default-name", name),
                    "type": itype,
                    "media_type": media_type,
                    "is_physical": is_physical,
                    "running": i.get("running") == "true",
                    "disabled": i.get("disabled") == "true",
                    "comment": i.get("comment", "") or eth_info.get("comment", ""),
                    "mac_address": i.get("mac-address") or eth_info.get("mac-address", "")
                })

            def _sort_key(iface):
                nm = iface["name"].lower()
                mt = iface.get("media_type")
                if mt == "ether" and not nm.startswith("sfp"):
                    cat = 1
                elif mt == "sfp" or nm.startswith("sfp"):
                    cat = 2
                elif mt == "wireless":
                    cat = 3
                elif iface.get("is_physical"):
                    cat = 4
                elif mt == "loopback" or nm == "lo":
                    cat = 99
                else:
                    cat = 50
                tokens = [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', nm)]
                return (cat, tokens)

            interfaces.sort(key=_sort_key)
            physical_interfaces = [i for i in interfaces if i.get("is_physical")]

            # 5. IP Addresses
            ip_list = api.get_resource('/ip/address').get()
            ip_map = {}
            for ip in ip_list:
                iface = ip.get("interface")
                addr = ip.get("address")
                if iface and addr:
                    ip_map[iface] = addr

            # 6. Active Hotspot Hosts & DHCP Leases
            hosts = []
            try:
                raw_hosts = api.get_resource('/ip/hotspot/host').get()
                bindings = api.get_resource('/ip/hotspot/ip-binding').get()
                leases = api.get_resource('/ip/dhcp-server/lease').get()
                bind_map = {b.get("mac-address", "").strip().upper(): b for b in bindings if b.get("mac-address")}
                lease_map = {l.get("mac-address", "").strip().upper(): l for l in leases if l.get("mac-address")}
                seen_macs = set()

                for rh in raw_hosts:
                    m = rh.get("mac-address", "").strip().upper()
                    if not m or m in seen_macs:
                        continue
                    seen_macs.add(m)
                    b_entry = bind_map.get(m, {})
                    l_entry = lease_map.get(m, {})
                    is_bypassed = rh.get("bypassed") == "true" or b_entry.get("type") == "bypassed"
                    rate = b_entry.get("rate-limit") or rh.get("rate-limit") or ""
                    comm = b_entry.get("comment") or rh.get("comment") or (l_entry.get("host-name") if l_entry else "") or ""
                    hosts.append({
                        "mac": m,
                        "address": rh.get("address") or rh.get("to-address") or "",
                        "interface": rh.get("interface") or rh.get("bridge") or "bridge-lan",
                        "bypassed": is_bypassed,
                        "rate_limit": rate,
                        "comment": comm,
                        "uptime": rh.get("uptime", ""),
                        "idle_time": rh.get("idle-time", "")
                    })

                for rl in leases:
                    m = rl.get("mac-address", "").strip().upper()
                    if not m or m in seen_macs or rl.get("status") != "bound":
                        continue
                    seen_macs.add(m)
                    b_entry = bind_map.get(m, {})
                    is_bypassed = b_entry.get("type") == "bypassed"
                    rate = b_entry.get("rate-limit") or ""
                    comm = b_entry.get("comment") or rl.get("host-name") or "DHCP Client"
                    hosts.append({
                        "mac": m,
                        "address": rl.get("active-address") or rl.get("address") or "",
                        "interface": rl.get("server") or "dhcp",
                        "bypassed": is_bypassed,
                        "rate_limit": rate,
                        "comment": comm,
                        "uptime": rl.get("expires-after", ""),
                        "idle_time": rl.get("last-seen", "")
                    })
            except Exception as e:
                logger.debug(f"Could not read hosts/leases from {self.host}: {e}")

            # Memory Calculations
            total_mem_bytes = int(res.get('total-memory', 0))
            free_mem_bytes = int(res.get('free-memory', 0))
            used_mem_bytes = max(0, total_mem_bytes - free_mem_bytes)
            total_mem_mb = round(total_mem_bytes / (1024 * 1024), 1)
            free_mem_mb = round(free_mem_bytes / (1024 * 1024), 1)
            used_mem_mb = round(used_mem_bytes / (1024 * 1024), 1)
            mem_percent = round((used_mem_bytes / total_mem_bytes * 100), 1) if total_mem_bytes > 0 else 0

            # CPU & Uptime
            cpu_load = int(res.get('cpu-load', 0))
            uptime = res.get('uptime', '0s')
            version = res.get('version', 'RouterOS')
            model = rb.get('model', res.get('board-name', 'hAP lite'))

            res_dict = {
                "connected": True,
                "host": self.host,
                "port": self.port,
                "latency_ms": latency_ms,
                "identity": identity,
                "model": model,
                "version": version,
                "cpu_model": res.get("cpu", "MIPS"),
                "cpu_load": cpu_load,
                "total_memory_mb": total_mem_mb,
                "free_memory_mb": free_mem_mb,
                "used_memory_mb": used_mem_mb,
                "memory_percent": mem_percent,
                "uptime": uptime,
                "interfaces": interfaces,
                "physical_interfaces": physical_interfaces,
                "ip_map": ip_map,
                "hosts": hosts,
                "error": None,
                "checked_at": time.strftime("%H:%M:%S")
            }
            self._live_status_cache = res_dict
            self._live_status_cache_time = time.time()
            return res_dict
        except Exception as e:
            latency_ms = round((time.time() - start_time) * 1000, 1)
            logger.error(f"Failed to connect to MikroTik at {self.host}:{self.port} - {e}")
            return {
                "connected": False,
                "host": self.host,
                "port": self.port,
                "latency_ms": latency_ms,
                "identity": "Disconnected",
                "model": "Unknown",
                "version": "N/A",
                "cpu_model": "N/A",
                "cpu_load": 0,
                "total_memory_mb": 0,
                "free_memory_mb": 0,
                "used_memory_mb": 0,
                "memory_percent": 0,
                "uptime": "Offline",
                "interfaces": [],
                "physical_interfaces": [],
                "ip_map": {},
                "hosts": [],
                "error": str(e),
                "checked_at": time.strftime("%H:%M:%S")
            }
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    def bind_device(
        self,
        mac_address: str,
        ip_address: Optional[str] = None,
        comment: str = "CyberNet Approved Device",
        rate_limit: Optional[str] = None
    ) -> bool:
        """
        Authorizes a device on MikroTik by adding or updating /ip/hotspot/ip-binding
        with type='bypassed'. Also clears any stale active hotspot sessions.
        """
        mac_clean = mac_address.strip().upper()
        if is_randomized_mac(mac_clean):
            logger.error(f"Refusing to bind randomized MAC address {mac_clean} on MikroTik. Physical Device MAC required.")
            return False

        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()

            # 1. /ip/hotspot/ip-binding
            binding_res = api.get_resource('/ip/hotspot/ip-binding')
            existing_bindings = binding_res.get()

            # Remove any existing binding(s) for this MAC address.
            # CRITICAL: We do NOT set the 'address' property on /ip/hotspot/ip-binding.
            # When 'address' is omitted, MikroTik bypasses the device purely by hardware MAC address
            # regardless of dynamic DHCP leases or IP reassignments. If 'address' were set,
            # any DHCP IP change after a device is away for 1 day/week/month causes an IP mismatch
            # and forces the customer to see the login screen again!
            for b in existing_bindings:
                if b.get('mac-address', '').upper() == mac_clean:
                    try:
                        binding_res.remove(id=b['id'])
                    except Exception as e:
                        logger.warning(f"Could not remove old binding {b.get('id')} for {mac_clean}: {e}")

            binding_res.add(
                **{
                    'mac-address': mac_clean,
                    'type': 'bypassed',
                    'comment': comment
                }
            )
            logger.info(f"Pushed pure MAC-only bypassed IP binding for {mac_clean} on {self.host}.")

            # 2. Clear any lingering unauthenticated active session
            try:
                active_res = api.get_resource('/ip/hotspot/active')
                for sess in active_res.get():
                    if sess.get('mac-address', '').upper() == mac_clean:
                        active_res.remove(id=sess['id'])
                        logger.info(f"Removed active hotspot session for {mac_clean}.")
            except Exception as e:
                logger.warning(f"Could not clear active session for {mac_clean}: {e}")

            # 3. Apply bandwidth limit via simple queue if requested
            norm_limit = normalize_rate_limit(rate_limit)
            q_name = f"hs-{mac_clean.replace(':', '')}"
            try:
                queue_res = api.get_resource('/queue/simple')
                existing_q = queue_res.get(name=q_name)
                if not norm_limit:
                    for eq in existing_q:
                        try:
                            queue_res.remove(id=eq['id'])
                        except Exception:
                            pass
                else:
                    target_ip = ip_address if (ip_address and not ip_address.startswith("10.20.30.") and ip_address != "127.0.0.1") else None
                    if not target_ip:
                        try:
                            for h in api.get_resource('/ip/hotspot/host').get():
                                if h.get('mac-address', '').upper() == mac_clean and h.get('address'):
                                    target_ip = h.get('address')
                                    break
                        except Exception:
                            pass
                    if not target_ip:
                        try:
                            for l in api.get_resource('/ip/dhcp-server/lease').get():
                                if l.get('mac-address', '').upper() == mac_clean and l.get('address'):
                                    target_ip = l.get('address')
                                    break
                        except Exception:
                            pass
                    if not target_ip:
                        try:
                            for b in existing_bindings:
                                if b.get('mac-address', '').upper() == mac_clean and b.get('address'):
                                    target_ip = b.get('address')
                                    break
                        except Exception:
                            pass
                    if target_ip:
                        if existing_q:
                            queue_res.set(id=existing_q[0]['id'], max_limit=norm_limit, target=target_ip)
                        else:
                            queue_res.add(name=q_name, target=target_ip, max_limit=norm_limit, comment=comment)
            except Exception as e:
                logger.warning(f"Could not set bandwidth limit for {mac_clean}: {e}")

            return True
        except Exception as e:
            logger.error(f"Failed to bind device {mac_clean} on MikroTik: {e}")
            return False
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    def _tear_down_session(self, api, mac_clean: str, ip_address: Optional[str] = None):
        """Internal helper to drop host, active session, cookie, and flushed conntrack."""
        client_ips = []
        if ip_address:
            client_ips.append(ip_address)

        try:
            host_res = api.get_resource('/ip/hotspot/host')
            for h in host_res.get():
                if h.get('mac-address', '').upper() == mac_clean:
                    h_ip = h.get('address')
                    if h_ip and h_ip not in client_ips:
                        client_ips.append(h_ip)
                    try:
                        host_res.remove(id=h['id'])
                        logger.info(f"Removed host entry for {mac_clean} ({h_ip})")
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Could not clear host entry for {mac_clean}: {e}")

        try:
            active_res = api.get_resource('/ip/hotspot/active')
            for a in active_res.get():
                if a.get('mac-address', '').upper() == mac_clean:
                    active_res.remove(id=a['id'])
                    logger.info(f"Removed active session for {mac_clean}")
        except Exception:
            pass

        try:
            cookie_res = api.get_resource('/ip/hotspot/cookie')
            for c in cookie_res.get():
                if c.get('mac-address', '').upper() == mac_clean:
                    cookie_res.remove(id=c['id'])
        except Exception:
            pass

        if client_ips:
            try:
                conn_res = api.get_resource('/ip/firewall/connection')
                flushed = 0
                for conn in conn_res.get():
                    conn_str = str(conn)
                    for ip in client_ips:
                        if ip in conn_str:
                            try:
                                conn_res.remove(id=conn['id'])
                                flushed += 1
                            except Exception:
                                pass
                logger.info(f"Flushed {flushed} active firewall connections for {client_ips}.")
            except Exception as e:
                logger.warning(f"Could not flush firewall connections: {e}")

        try:
            queue_res = api.get_resource('/queue/simple')
            q_name = f"hs-{mac_clean.replace(':', '')}"
            for q in queue_res.get():
                if q.get('name') == q_name:
                    queue_res.remove(id=q['id'])
        except Exception:
            pass

    def block_device(
        self,
        mac_address: str,
        ip_address: Optional[str] = None,
        comment: str = "CyberNet: Blocked (Randomized MAC)"
    ) -> bool:
        """
        Actively blocks a MAC address on MikroTik RouterOS by creating or updating
        /ip/hotspot/ip-binding with type='blocked', removing any active sessions,
        hosts, cookies, and flushing firewall connections.
        """
        mac_clean = mac_address.strip().upper()
        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()

            # 1. /ip/hotspot/ip-binding: Set type=blocked (pure MAC-only)
            binding_res = api.get_resource('/ip/hotspot/ip-binding')
            existing_bindings = binding_res.get()
            for b in existing_bindings:
                if b.get('mac-address', '').upper() == mac_clean:
                    try:
                        binding_res.remove(id=b['id'])
                    except Exception:
                        pass

            binding_res.add(
                **{
                    'mac-address': mac_clean,
                    'type': 'blocked',
                    'comment': comment
                }
            )
            logger.info(f"Created pure MAC-only BLOCKED IP binding for {mac_clean} on {self.host}.")

            # 2. Teardown active hotspot sessions, hosts, and conntracks
            self._tear_down_session(api, mac_clean, ip_address)
            return True
        except Exception as e:
            logger.error(f"Failed to block device {mac_clean} on MikroTik: {e}")
            return False
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    def unbind_device(self, mac_address: str, ip_address: Optional[str] = None) -> bool:
        """
        Instantly revokes and cuts off device authorization from MikroTik:
        1. Removes /ip/hotspot/ip-binding.
        2. Removes host entry from /ip/hotspot/host.
        3. Kills active hotspot session in /ip/hotspot/active.
        4. Clears cookies from /ip/hotspot/cookie.
        5. Flushes all established TCP/UDP streams in /ip/firewall/connection (cuts active internet instantly!).
        6. Removes client rate-limit queue in /queue/simple.
        """
        mac_clean = mac_address.strip().upper()
        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()

            # 1. Remove from /ip/hotspot/ip-binding
            binding_res = api.get_resource('/ip/hotspot/ip-binding')
            for b in binding_res.get():
                if b.get('mac-address', '').upper() == mac_clean:
                    binding_res.remove(id=b['id'])
                    logger.info(f"Removed IP binding for {mac_clean}")

            # 2. Teardown host, session, cookie, conntrack, queue
            self._tear_down_session(api, mac_clean, ip_address)
            return True
        except Exception as e:
            logger.error(f"Failed to unbind device {mac_clean}: {e}")
            return False
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    def sync_package_profile(
        self,
        profile_name: str,
        rate_limit: Optional[str] = None,
        shared_users: int = 1,
        package_type: str = "hotspot"
    ) -> bool:
        """
        Provisions or updates a user profile on MikroTik RouterOS:
        - For Hotspot: /ip/hotspot/user/profile (with shared-users & rate-limit)
        - For PPPoE: /ppp/profile (with rate-limit)
        If rate_limit is "0", "0M/0M", empty, or "unlimited", rate-limit is explicitly set to "" (full unlimited speed).
        """
        clean_prof = profile_name.strip() if profile_name else "default"
        clean_type = package_type.strip().lower() if package_type else "hotspot"

        # Check unlimited
        unlimited = not rate_limit or rate_limit.strip().lower() in ("0", "0m", "0k", "0/0", "0m/0m", "unlimited", "none", "")
        effective_rate = "" if unlimited else rate_limit.strip()

        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()

            if clean_type == "hotspot":
                res = api.get_resource("/ip/hotspot/user/profile")
                existing = res.get(name=clean_prof)
                params = {
                    "shared-users": str(max(1, int(shared_users))),
                    "rate-limit": effective_rate
                }
                if existing:
                    res.set(id=existing[0]["id"], **params)
                    logger.info(f"Updated Hotspot profile '{clean_prof}' on MikroTik: rate-limit='{effective_rate}' (Unlimited={unlimited})")
                else:
                    params["name"] = clean_prof
                    res.add(**params)
                    logger.info(f"Created Hotspot profile '{clean_prof}' on MikroTik: rate-limit='{effective_rate}' (Unlimited={unlimited})")
                return True

            elif clean_type == "pppoe":
                res = api.get_resource("/ppp/profile")
                existing = res.get(name=clean_prof)
                params = {
                    "rate-limit": effective_rate,
                    "local-address": "10.44.0.1",
                    "remote-address": "pool-pppoe-ether4",
                    "dns-server": "8.8.8.8,1.1.1.1",
                    "change-tcp-mss": "yes"
                }
                if existing:
                    # Update without overriding existing custom local/remote if present
                    upd_params = {"rate-limit": effective_rate, "change-tcp-mss": "yes"}
                    if not existing[0].get("local-address"):
                        upd_params["local-address"] = "10.44.0.1"
                    if not existing[0].get("remote-address"):
                        upd_params["remote-address"] = "pool-pppoe-ether4"
                    if not existing[0].get("dns-server"):
                        upd_params["dns-server"] = "8.8.8.8,1.1.1.1"
                    res.set(id=existing[0]["id"], **upd_params)
                    logger.info(f"Updated PPPoE profile '{clean_prof}' on MikroTik: rate-limit='{effective_rate}' (Unlimited={unlimited})")
                else:
                    params["name"] = clean_prof
                    res.add(**params)
                    logger.info(f"Created PPPoE profile '{clean_prof}' on MikroTik: rate-limit='{effective_rate}' (Unlimited={unlimited})")
                return True

            return False
        except Exception as e:
            logger.error(f"Failed to sync package profile '{clean_prof}' on MikroTik: {e}")
            return False
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    def delete_package_profile(self, profile_name: str, package_type: str = "hotspot") -> bool:
        """Removes a user profile from MikroTik RouterOS."""
        clean_prof = profile_name.strip() if profile_name else ""
        if not clean_prof or clean_prof == "default":
            return False

        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()
            path = "/ip/hotspot/user/profile" if package_type.lower() == "hotspot" else "/ppp/profile"
            res = api.get_resource(path)
            existing = res.get(name=clean_prof)
            if existing:
                res.remove(id=existing[0]["id"])
                logger.info(f"Removed profile '{clean_prof}' from MikroTik ({path})")
            return True
        except Exception as e:
            logger.error(f"Failed to delete profile '{clean_prof}' from MikroTik: {e}")
            return False
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    # =========================================================================
    # PPPoE SUBSCRIBER MANAGEMENT & REAL-TIME SYNCHRONIZATION
    # =========================================================================
    def sync_pppoe_secret(
        self,
        username: str,
        password: str,
        profile: Optional[str] = None,
        remote_ip: Optional[str] = None,
        local_ip: Optional[str] = None,
        rate_limit: Optional[str] = None,
        disabled: bool = False,
        comment: str = ""
    ) -> bool:
        """
        Provisions or updates a PPPoE subscriber credential in /ppp/secret on MikroTik.
        Supports speed rate-limits via auto-provisioned profiles, static remote IP,
        and suspension toggle with immediate session termination.
        """
        clean_user = (username or "").strip()
        clean_pass = (password or "").strip()
        if not clean_user or not clean_pass:
            logger.error("sync_pppoe_secret requires valid username and password.")
            return False

        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()

            # Profile resolution & rate limit handling
            selected_profile = profile.strip() if profile and profile.strip() else "pppoe-profile-ether4"
            norm_rate = normalize_rate_limit(rate_limit)

            if norm_rate:
                custom_prof_name = f"pppoe-{norm_rate.replace('/', '-').lower()}"
                try:
                    prof_res = api.get_resource('/ppp/profile')
                    existing_p = prof_res.get(name=custom_prof_name)
                    if not existing_p:
                        prof_res.add(
                            name=custom_prof_name,
                            **{
                                'local-address': local_ip or '10.44.0.1',
                                'remote-address': 'pool-pppoe-ether4',
                                'rate-limit': norm_rate,
                                'dns-server': '8.8.8.8,1.1.1.1',
                                'change-tcp-mss': 'yes'
                            }
                        )
                        logger.info(f"Auto-created speed profile '{custom_prof_name}' ({norm_rate}) on {self.host}")
                    selected_profile = custom_prof_name
                except Exception as pe:
                    logger.warning(f"Could not ensure rate profile {custom_prof_name}: {pe}")

            sec_res = api.get_resource('/ppp/secret')
            existing_secs = sec_res.get(name=clean_user)

            params = {
                'name': clean_user,
                'password': clean_pass,
                'service': 'pppoe',
                'profile': selected_profile,
                'disabled': 'yes' if disabled else 'no',
                'comment': comment or f"CyberNet PPPoE: {clean_user}"
            }
            if remote_ip and remote_ip.strip():
                params['remote-address'] = remote_ip.strip()
            if local_ip and local_ip.strip():
                params['local-address'] = local_ip.strip()

            if existing_secs:
                sec_res.set(id=existing_secs[0]['id'], **params)
                logger.info(f"Updated /ppp/secret for '{clean_user}' (profile={selected_profile}, disabled={disabled}) on {self.host}")
            else:
                sec_res.add(**params)
                logger.info(f"Created /ppp/secret for '{clean_user}' (profile={selected_profile}, disabled={disabled}) on {self.host}")

            # If disabled (e.g. customer suspended or cut off), kick active connection immediately!
            if disabled:
                try:
                    act_res = api.get_resource('/ppp/active')
                    for act in act_res.get(name=clean_user):
                        act_res.remove(id=act['id'])
                        logger.info(f"Terminated active PPPoE session for suspended user '{clean_user}' on {self.host}")
                except Exception as ae:
                    logger.warning(f"Could not terminate active PPPoE session for {clean_user}: {ae}")

            return True
        except Exception as e:
            logger.error(f"Failed to sync PPPoE secret for '{clean_user}' on {self.host}: {e}")
            return False
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    def remove_pppoe_secret(self, username: str) -> bool:
        """Removes /ppp/secret and terminates active session for username on MikroTik."""
        clean_user = (username or "").strip()
        if not clean_user:
            return False
        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()
            sec_res = api.get_resource('/ppp/secret')
            for s in sec_res.get(name=clean_user):
                sec_res.remove(id=s['id'])
                logger.info(f"Removed /ppp/secret for '{clean_user}' on {self.host}")

            try:
                act_res = api.get_resource('/ppp/active')
                for act in act_res.get(name=clean_user):
                    act_res.remove(id=act['id'])
                    logger.info(f"Terminated active PPPoE session for removed user '{clean_user}' on {self.host}")
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"Failed to remove PPPoE secret for '{clean_user}' on {self.host}: {e}")
            return False
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    def toggle_pppoe_secret(self, username: str, disabled: bool = True) -> bool:
        """Enables or disables /ppp/secret on MikroTik. Kicks active session if disabling."""
        clean_user = (username or "").strip()
        if not clean_user:
            return False
        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()
            sec_res = api.get_resource('/ppp/secret')
            existing = sec_res.get(name=clean_user)
            if not existing:
                logger.warning(f"/ppp/secret for '{clean_user}' not found on {self.host} during toggle")
                return False

            sec_res.set(id=existing[0]['id'], disabled='yes' if disabled else 'no')
            logger.info(f"Toggled /ppp/secret for '{clean_user}' to disabled={disabled} on {self.host}")

            if disabled:
                try:
                    act_res = api.get_resource('/ppp/active')
                    for act in act_res.get(name=clean_user):
                        act_res.remove(id=act['id'])
                        logger.info(f"Kicked active PPPoE session for '{clean_user}' on {self.host}")
                except Exception:
                    pass
            return True
        except Exception as e:
            logger.error(f"Failed to toggle PPPoE secret for '{clean_user}' on {self.host}: {e}")
            return False
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    def get_active_pppoe_sessions(self) -> List[Dict[str, Any]]:
        """Fetches all currently connected PPPoE sessions from /ppp/active."""
        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()
            active_res = api.get_resource('/ppp/active')
            sessions = active_res.get()
            clean = []
            for s in sessions:
                clean.append({
                    "id": s.get("id"),
                    "name": s.get("name"),
                    "service": s.get("service", "pppoe"),
                    "caller_id": s.get("caller-id", ""),
                    "address": s.get("address", ""),
                    "uptime": s.get("uptime", ""),
                    "encoding": s.get("encoding", "")
                })
            return clean
        except Exception as e:
            logger.error(f"Failed to fetch /ppp/active from {self.host}: {e}")
            return []
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    def get_pppoe_secrets(self) -> List[Dict[str, Any]]:
        """Queries /ppp/secret from this router."""
        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()
            return api.get_resource('/ppp/secret').get()
        except Exception as e:
            logger.error(f"Failed to fetch /ppp/secret from {self.host}: {e}")
            return []
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    def get_pppoe_sessions_map(self) -> Dict[str, Dict[str, Any]]:
        """Returns map of {username: session_data} for fast O(1) lookup."""
        sessions = self.get_active_pppoe_sessions()
        return {s["name"]: s for s in sessions if s.get("name")}

    def disconnect_pppoe_session(self, username: str) -> bool:
        """Terminates an active session from /ppp/active for username."""
        clean_user = (username or "").strip()
        if not clean_user:
            return False
        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()
            act_res = api.get_resource('/ppp/active')
            for act in act_res.get(name=clean_user):
                act_res.remove(id=act['id'])
                logger.info(f"Disconnected active PPPoE session for '{clean_user}' on {self.host}")
            return True
        except Exception as e:
            logger.error(f"Failed to disconnect PPPoE session for '{clean_user}' on {self.host}: {e}")
            return False
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    def update_device_speed_limit(
        self,
        mac_address: str,
        ip_address: Optional[str] = None,
        rate_limit: Optional[str] = None,
        comment: str = ""
    ) -> bool:
        """
        Sets or clears bandwidth limit in /queue/simple for a specific device MAC on MikroTik.
        If rate_limit is None or unlimited, removes any queue for this device.
        If rate_limit is set, creates or updates /queue/simple targeting device IP.
        """
        mac_clean = mac_address.strip().upper()
        norm_limit = normalize_rate_limit(rate_limit)
        q_name = f"hs-{mac_clean.replace(':', '')}"

        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()
            queue_res = api.get_resource('/queue/simple')
            existing_queues = queue_res.get(name=q_name)

            if not norm_limit:
                # Unlimited speed requested: remove existing queue
                for q in existing_queues:
                    try:
                        queue_res.remove(id=q['id'])
                        logger.info(f"Removed speed limit queue {q_name} (now Unlimited).")
                    except Exception:
                        pass
                return True

            # If ip_address not provided, discover it
            target_ip = ip_address
            if not target_ip:
                # 1. Check /ip/hotspot/host
                try:
                    for h in api.get_resource('/ip/hotspot/host').get():
                        if h.get('mac-address', '').upper() == mac_clean and h.get('address'):
                            target_ip = h.get('address')
                            break
                except Exception:
                    pass

                # 2. Check /ip/dhcp-server/lease
                if not target_ip:
                    try:
                        for l in api.get_resource('/ip/dhcp-server/lease').get():
                            if l.get('mac-address', '').upper() == mac_clean and l.get('address'):
                                target_ip = l.get('address')
                                break
                    except Exception:
                        pass

                # 3. Check /ip/hotspot/ip-binding
                if not target_ip:
                    try:
                        for b in api.get_resource('/ip/hotspot/ip-binding').get():
                            if b.get('mac-address', '').upper() == mac_clean and b.get('address'):
                                target_ip = b.get('address')
                                break
                    except Exception:
                        pass

            if not target_ip:
                logger.warning(f"Could not find live IP for device MAC {mac_clean} to apply queue.")
                return False

            if existing_queues:
                queue_res.set(id=existing_queues[0]['id'], max_limit=norm_limit, target=target_ip)
                logger.info(f"Updated queue {q_name} for IP {target_ip} with max_limit={norm_limit}")
            else:
                queue_res.add(name=q_name, target=target_ip, max_limit=norm_limit, comment=comment or f"Speed Limit for {mac_clean}")
                logger.info(f"Created queue {q_name} for IP {target_ip} with max_limit={norm_limit}")

            return True
        except Exception as e:
            logger.error(f"Failed to update device speed limit on MikroTik for {mac_clean}: {e}")
            return False
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    def sync_customer_devices_speed(
        self,
        devices: List[Dict[str, Any]],
        rate_limit: Optional[str],
        comment: str = ""
    ) -> bool:
        """
        Updates the speed limit on MikroTik for all authorized devices of a customer.
        """
        success = True
        for dev in devices:
            if dev.get("status") == "approved":
                ok = self.update_device_speed_limit(
                    mac_address=dev["mac_address"],
                    ip_address=dev.get("ip_address"),
                    rate_limit=rate_limit,
                    comment=comment
                )
                if not ok:
                    success = False
        return success

    def get_simple_queues(self) -> List[Dict[str, Any]]:
        """
        Fetches all simple queues (/queue/simple) configured on this MikroTik router.
        Returns detailed list with name, target IP, max-limit (upload/download),
        current rate, and total bytes transferred.
        """
        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()
            raw_queues = api.get_resource('/queue/simple').get()
            queues = []
            for q in raw_queues:
                max_l = q.get('max-limit', '0/0')
                up_str, down_str = '0', '0'
                if '/' in max_l:
                    parts = max_l.split('/')
                    try:
                        up_val = int(parts[0])
                        down_val = int(parts[1])
                        up_str = f"{up_val // 1000000}M" if up_val >= 1000000 else f"{up_val // 1000}k" if up_val > 0 else "Unlimited"
                        down_str = f"{down_val // 1000000}M" if down_val >= 1000000 else f"{down_val // 1000}k" if down_val > 0 else "Unlimited"
                    except Exception:
                        up_str, down_str = parts[0], parts[1]

                bytes_str = q.get('bytes', '0/0')
                up_bytes, down_bytes = 0, 0
                if '/' in bytes_str:
                    try:
                        b_parts = bytes_str.split('/')
                        up_bytes = int(b_parts[0])
                        down_bytes = int(b_parts[1])
                    except Exception:
                        pass

                rate_str = q.get('rate', '0/0')
                up_rate, down_rate = '0 bps', '0 bps'
                if '/' in rate_str:
                    try:
                        r_parts = rate_str.split('/')
                        r_up = int(r_parts[0])
                        r_down = int(r_parts[1])
                        up_rate = f"{r_up / 1000000:.1f} Mbps" if r_up >= 1000000 else f"{r_up / 1000:.0f} kbps" if r_up > 0 else "0 bps"
                        down_rate = f"{r_down / 1000000:.1f} Mbps" if r_down >= 1000000 else f"{r_down / 1000:.0f} kbps" if r_down > 0 else "0 bps"
                    except Exception:
                        pass

                queues.append({
                    "id": q.get('id'),
                    "name": q.get('name'),
                    "target": q.get('target'),
                    "max_limit_raw": max_l,
                    "max_limit_formatted": f"▲ {up_str} / ▼ {down_str}",
                    "upload_limit": up_str,
                    "download_limit": down_str,
                    "current_rate": f"▲ {up_rate} / ▼ {down_rate}",
                    "upload_bytes": up_bytes,
                    "download_bytes": down_bytes,
                    "total_bytes_formatted": format_bytes(up_bytes + down_bytes),
                    "dropped": q.get('dropped', '0/0'),
                    "disabled": q.get('disabled') == 'true',
                    "comment": q.get('comment', '')
                })
            return queues
        except Exception as e:
            logger.error(f"Failed to fetch simple queues from {self.host}: {e}")
            return []
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    def get_devices_usage(self, mac_addresses: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetches real-time internet session and traffic usage metrics for given MAC addresses
        from MikroTik /ip/hotspot/host and /ip/dhcp-server/lease.
        Returns a dict mapping normalized MAC to usage telemetry.
        """
        results: Dict[str, Dict[str, Any]] = {}
        target_macs = {m.strip().upper() for m in mac_addresses if m and m.strip()}
        if not target_macs:
            return results

        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()

            # 1. Hotspot Hosts (Live sessions, uptime, bytes in/out)
            hosts = []
            try:
                hosts = api.get_resource('/ip/hotspot/host').get()
            except Exception as e:
                logger.warning(f"Could not read hotspot hosts: {e}")

            # 2. DHCP Leases (Host names, IP, last-seen)
            leases = []
            try:
                leases = api.get_resource('/ip/dhcp-server/lease').get()
            except Exception as e:
                logger.warning(f"Could not read DHCP leases: {e}")

            host_map = {h.get("mac-address", "").upper(): h for h in hosts if h.get("mac-address")}
            lease_map = {l.get("mac-address", "").upper(): l for l in leases if l.get("mac-address")}

            for mac in target_macs:
                host_info = host_map.get(mac, {})
                lease_info = lease_map.get(mac, {})

                raw_in = int(host_info.get("bytes-in", 0) or 0)
                raw_out = int(host_info.get("bytes-out", 0) or 0)
                total_bytes = raw_in + raw_out

                ip_addr = host_info.get("address") or lease_info.get("active-address") or lease_info.get("address") or "—"
                uptime = host_info.get("uptime") or "—"
                last_seen = lease_info.get("last-seen") or "—"
                host_name = lease_info.get("host-name") or "Mobile / Client Device"
                status_str = "Online" if (host_info or lease_info.get("status") == "bound") else "Offline"

                results[mac] = {
                    "mac_address": mac,
                    "is_online": (status_str == "Online"),
                    "status": status_str,
                    "ip_address": ip_addr,
                    "host_name": host_name,
                    "uptime": uptime,
                    "last_seen": last_seen,
                    "idle_time": host_info.get("idle-time", "—"),
                    "upload_bytes": raw_in,
                    "download_bytes": raw_out,
                    "total_bytes": total_bytes,
                    "upload_formatted": format_bytes(raw_in),
                    "download_formatted": format_bytes(raw_out),
                    "total_formatted": format_bytes(total_bytes),
                    "packets_in": int(host_info.get("packets-in", 0) or 0),
                    "packets_out": int(host_info.get("packets-out", 0) or 0)
                }

            return results
        except Exception as e:
            logger.error(f"Error fetching device usage from MikroTik: {e}")
            return results
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    def get_online_mac_addresses(self, max_cache_age_sec: float = 5.0) -> List[str]:
        """
        Fetches all MAC addresses currently active in /ip/hotspot/host and bound in /ip/dhcp-server/lease.
        Cached in memory for max_cache_age_sec to prevent high-frequency socket bottlenecks.
        """
        now = time.time()
        if self._online_macs_cache is not None and (now - self._online_macs_cache_time) < max_cache_age_sec:
            return self._online_macs_cache

        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()
            active_macs = set()

            # 1. Hotspot hosts
            try:
                hosts = api.get_resource('/ip/hotspot/host').get()
                for h in hosts:
                    m = h.get('mac-address')
                    if m:
                        active_macs.add(m.strip().upper())
            except Exception as e:
                logger.warning(f"Could not read hotspot hosts: {e}")

            # 2. Bound DHCP leases
            try:
                leases = api.get_resource('/ip/dhcp-server/lease').get()
                for l in leases:
                    if l.get('status') == 'bound' and l.get('mac-address'):
                        active_macs.add(l.get('mac-address').strip().upper())
            except Exception as e:
                logger.warning(f"Could not read DHCP leases: {e}")

            mac_list = list(active_macs)
            self._online_macs_cache = mac_list
            self._online_macs_cache_time = time.time()
            return mac_list
        except Exception as e:
            logger.warning(f"Could not fetch online MAC addresses from MikroTik: {e}")
            return []
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    def get_devices_telemetry_map(self, max_cache_age_sec: float = 5.0) -> Dict[str, Dict[str, Any]]:
        """
        Fetches live network telemetry for all devices across the router.
        Combines /ip/hotspot/host and /ip/dhcp-server/lease in a single quick call.
        Results are cached in memory for max_cache_age_sec to avoid duplicate socket connections.
        
        Returns a dict mapping normalized MAC (e.g. '3C:38:24:0F:69:74') to telemetry:
            - state: 'online' (green), 'recent' (yellow), 'offline' (red)
            - status_label: 'Online', 'Recently Offline', 'Offline'
            - is_online: bool
            - live_ip: str or None
            - dhcp_host_name: str or None
            - uptime: str or None
            - last_seen: str or None
            - idle_time: str or None
            - detail: human-friendly description
        """
        now = time.time()
        if self._telemetry_cache is not None and (now - self._telemetry_cache_time) < max_cache_age_sec:
            return self._telemetry_cache

        self.refresh_from_db()
        pool = None
        telemetry: Dict[str, Dict[str, Any]] = {}
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()

            # 1. Hotspot Hosts (live sessions, uptime, idle time, IP)
            hosts = []
            try:
                hosts = api.get_resource('/ip/hotspot/host').get()
            except Exception as e:
                logger.warning(f"Could not read hotspot hosts: {e}")

            # 2. DHCP Leases (host-name, lease status, last-seen)
            leases = []
            try:
                leases = api.get_resource('/ip/dhcp-server/lease').get()
            except Exception as e:
                logger.warning(f"Could not read DHCP leases: {e}")

            # 3. Hotspot Sharing Suspects (Tethering attempts detected via ingress TTL=63 / TTL=127)
            sharing_ips: Dict[str, Dict[str, Any]] = {}
            try:
                addr_list = api.get_resource('/ip/firewall/address-list').get(list='hotspot_sharing_suspects')
                for ae in addr_list:
                    addr = ae.get('address')
                    if addr:
                        sharing_ips[addr.strip()] = ae
            except Exception as e:
                logger.debug(f"Could not read hotspot_sharing_suspects from {self.host}: {e}")

            host_map: Dict[str, Dict[str, Any]] = {}
            for h in hosts:
                m = h.get("mac-address")
                if m:
                    host_map[m.strip().upper()] = h

            lease_map: Dict[str, Dict[str, Any]] = {}
            for l in leases:
                m = l.get("mac-address")
                if m:
                    lease_map[m.strip().upper()] = l

            all_router_macs = set(host_map.keys()) | set(lease_map.keys())

            for mac in all_router_macs:
                h = host_map.get(mac)
                l = lease_map.get(mac)

                last_seen_str = l.get("last-seen") if l else None
                last_seen_sec = parse_routeros_duration(last_seen_str)
                idle_str = h.get("idle-time") if h else None
                idle_sec = parse_routeros_duration(idle_str)
                uptime_str = h.get("uptime") if h else None
                dhcp_host_name = l.get("host-name") if l else None
                lease_status = l.get("status") if l else None
                live_ip = (h.get("address") if h else None) or (l.get("active-address") or l.get("address") if l else None)

                # Classification:
                # 🟢 Online: In active hotspot host table OR bound in DHCP with last-seen <= 300s
                # (unless idle for > 15m without any hotspot activity)
                if h:
                    if idle_sec is not None and idle_sec > 900:
                        state = "recent"
                        status_label = "Recently Offline"
                        detail = f"Idle {idle_str}"
                    else:
                        state = "online"
                        status_label = "Online"
                        detail = f"Up {uptime_str}" if uptime_str else "Online"
                elif l and lease_status == "bound" and last_seen_sec is not None and last_seen_sec <= 300:
                    state = "online"
                    status_label = "Online"
                    detail = f"Seen {last_seen_str} ago"
                elif last_seen_sec is not None and last_seen_sec <= 3600:
                    # 🟡 Recently Offline: Seen in DHCP lease within the last 1 hour
                    state = "recent"
                    status_label = "Recently Offline"
                    detail = f"Seen {last_seen_str} ago"
                else:
                    # 🔴 Offline
                    state = "offline"
                    status_label = "Offline"
                    detail = f"Last seen {last_seen_str}" if last_seen_str else "Offline"

                # Check tethering detection
                is_sharing = bool(live_ip and live_ip.strip() in sharing_ips)
                sharing_entry = sharing_ips.get(live_ip.strip(), {}) if is_sharing else {}
                sharing_timeout = sharing_entry.get("timeout")
                sharing_detail = f"Hotspot sharing attempt detected (Blocked via TTL=1)" if is_sharing else None

                telemetry[mac] = {
                    "mac_address": mac,
                    "state": state,
                    "status_label": status_label,
                    "is_online": (state == "online"),
                    "live_ip": live_ip,
                    "dhcp_host_name": dhcp_host_name,
                    "uptime": uptime_str,
                    "last_seen": last_seen_str,
                    "idle_time": idle_str,
                    "detail": detail,
                    "is_sharing_hotspot": is_sharing,
                    "sharing_timeout": sharing_timeout,
                    "sharing_detail": sharing_detail
                }

            self._telemetry_cache = telemetry
            self._telemetry_cache_time = now
            return telemetry
        except Exception as e:
            logger.error(f"Error fetching device telemetry map from MikroTik: {e}")
            if self._telemetry_cache is not None:
                return self._telemetry_cache
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    def get_hotspot_hosts_raw(self) -> List[Dict[str, Any]]:
        """
        Fetches raw /ip/hotspot/host entries with bytes-in, bytes-out, uptime, address, and mac-address.
        Used by the background Internet Traffic Accounting Collector to compute delta usage.
        """
        self.refresh_from_db()
        pool = None
        try:
            pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()
            return api.get_resource('/ip/hotspot/host').get()
        except Exception as e:
            logger.debug(f"Could not read hotspot hosts: {e}")
            return []
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass


# =========================================================
# MULTI-ROUTER FLEET ROAMING & SYNC HELPERS
# =========================================================

def test_router_connection(
    host: str,
    username: str = "admin",
    password: str = "",
    port: int = 8728
) -> Dict[str, Any]:
    """
    Tests live connectivity to a specific MikroTik router and retrieves hardware specs.
    """
    start_time = time.time()
    pool = None
    use_ssl = (port == 8729)
    try:
        pool = routeros_api.RouterOsApiPool(
            host,
            username=username,
            password=password,
            port=port,
            use_ssl=use_ssl,
            ssl_verify=False,
            plaintext_login=True
        )
        api = pool.get_api()
        latency_ms = round((time.time() - start_time) * 1000, 1)

        # 1. Resource
        res_list = api.get_resource('/system/resource').get()
        res = res_list[0] if res_list else {}

        # 2. Identity
        ident_list = api.get_resource('/system/identity').get()
        identity = ident_list[0].get('name', 'MikroTik') if ident_list else 'MikroTik'

        # 3. RouterBoard Model
        model = "RouterOS"
        try:
            rb_list = api.get_resource('/system/routerboard').get()
            if rb_list:
                model = rb_list[0].get('model') or rb_list[0].get('board-name') or "RouterOS"
        except Exception:
            pass

        return {
            "success": True,
            "latency_ms": latency_ms,
            "identity": identity,
            "model": model,
            "version": res.get("version", "Unknown"),
            "cpu_usage": int(res.get("cpu-load", 0)),
            "uptime": res.get("uptime", "Unknown")
        }
    except Exception as e:
        logger.warning(f"Connection test failed for {host}:{port}: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        if pool is not None:
            try:
                pool.disconnect()
            except Exception:
                pass


def get_client_for_router(r_dict: Dict[str, Any]) -> RouterClient:
    """Instantiates a RouterClient from a router record dictionary."""
    port = r_dict.get("port", 8728)
    use_ssl = (port == 8729 or bool(r_dict.get("use_ssl", False)))
    return RouterClient(
        host=r_dict["host"],
        username=r_dict["username"],
        password=r_dict["password"],
        port=port,
        use_ssl=use_ssl,
        router_id=r_dict.get("id")
    )


_fleet_telemetry_cache: Optional[Dict[str, Dict[str, Any]]] = None
_fleet_telemetry_cache_time: float = 0.0


def get_router_short_code(router_name: Optional[str] = None, router_id: Optional[int] = None) -> str:
    """
    Extracts short hardware code (e.g. MK10, MK20, MK30) from router name or ID.
    """
    name_l = (router_name or "").lower()
    if "10" in name_l:
        return "MK10"
    if "20" in name_l:
        return "MK20"
    if "30" in name_l:
        return "MK30"
    if router_id is not None:
        return f"MK{router_id}"
    return "MK"


def broadcast_get_devices_telemetry_map(max_cache_age_sec: float = 4.0) -> Dict[str, Dict[str, Any]]:
    """
    Queries ALL active MikroTik routers in the fleet concurrently using ThreadPoolExecutor.
    Intelligently reconciles multi-gateway roaming states:
    - If a device is seen on multiple routers (e.g. roamed from MK10 to MK20),
      an 'online' state on ANY router strictly overrides 'recent' or 'offline' states.
    - If online on multiple routers, selects the router with the lowest idle_time.
    - Accurately attributes active router short code (MK10, MK20, MK30), live IP,
      and roaming indicator (is_roaming=True).
    Cached in memory for max_cache_age_sec (default 4.0s) to keep CPU low and API sub-millisecond.
    """
    global _fleet_telemetry_cache, _fleet_telemetry_cache_time
    now = time.time()
    if _fleet_telemetry_cache is not None and (now - _fleet_telemetry_cache_time) < max_cache_age_sec:
        return _fleet_telemetry_cache

    import database
    try:
        routers = database.get_all_routers(active_only=True)
    except Exception as e:
        logger.warning(f"Could not load active routers for fleet telemetry: {e}")
        routers = []

    if not routers:
        return {}

    def _fetch_for_router(r):
        try:
            client = get_client_for_router(r)
            tmap = client.get_devices_telemetry_map(max_cache_age_sec=0)
            return r, tmap, None
        except Exception as e:
            logger.debug(f"Fleet telemetry fetch failed for router {r.get('id')} ({r.get('name')}): {e}")
            return r, {}, str(e)

    with ThreadPoolExecutor(max_workers=len(routers) or 1) as executor:
        results = list(executor.map(_fetch_for_router, routers))

    all_mac_appearances: Dict[str, List[Any]] = {}
    for r, tmap, err in results:
        r_name = r.get("name") or f"Router {r.get('id')}"
        short_code = get_router_short_code(r_name, r.get("id"))
        for mac, telem in tmap.items():
            if mac not in all_mac_appearances:
                all_mac_appearances[mac] = []
            telem_copy = dict(telem)
            telem_copy["router_id"] = r.get("id")
            telem_copy["router_name"] = r_name
            telem_copy["router_short_name"] = short_code
            all_mac_appearances[mac].append((r, telem_copy))

    fleet_telemetry: Dict[str, Dict[str, Any]] = {}

    for mac, appearances in all_mac_appearances.items():
        is_roaming = len(appearances) > 1
        roaming_short_codes = [get_router_short_code(r.get("name"), r.get("id")) for r, _ in appearances]

        online_entries = [t for _, t in appearances if t.get("state") == "online"]
        recent_entries = [t for _, t in appearances if t.get("state") == "recent"]
        offline_entries = [t for _, t in appearances if t.get("state") == "offline"]

        if online_entries:
            best = online_entries[0]
            if len(online_entries) > 1:
                def get_idle(t):
                    sec = parse_routeros_duration(t.get("idle_time"))
                    return sec if sec is not None else 999999
                best = min(online_entries, key=get_idle)

            final_telem = dict(best)
            final_telem["state"] = "online"
            final_telem["is_online"] = True
            final_telem["is_roaming"] = is_roaming
            final_telem["roaming_routers"] = roaming_short_codes
            active_code = final_telem.get("router_short_name", "MK")
            other_codes = [c for c in roaming_short_codes if c != active_code]
            if is_roaming:
                if other_codes:
                    final_telem["roaming_label"] = f"Roaming Active on {active_code} (also on {', '.join(other_codes)})"
                    final_telem["status_label"] = f"Online ({active_code} Roaming)"
                else:
                    final_telem["roaming_label"] = f"Roaming Active on {active_code}"
                    final_telem["status_label"] = f"Online ({active_code})"
            else:
                final_telem["roaming_label"] = f"Connected on {active_code}"
                final_telem["status_label"] = f"Online ({active_code})"

        elif recent_entries:
            def get_seen(t):
                sec = parse_routeros_duration(t.get("last_seen"))
                return sec if sec is not None else 999999
            best = min(recent_entries, key=get_seen)
            final_telem = dict(best)
            final_telem["state"] = "recent"
            final_telem["is_online"] = False
            final_telem["is_roaming"] = is_roaming
            final_telem["roaming_routers"] = roaming_short_codes
            active_code = final_telem.get("router_short_name", "MK")
            if is_roaming:
                final_telem["roaming_label"] = f"Recently on {active_code} (Roamed across {', '.join(roaming_short_codes)})"
                final_telem["status_label"] = f"Recently Offline ({active_code})"
            else:
                final_telem["roaming_label"] = f"Recently on {active_code}"
                final_telem["status_label"] = f"Recently Offline ({active_code})"

        else:
            best = offline_entries[0] if offline_entries else {}
            final_telem = dict(best)
            final_telem["state"] = "offline"
            final_telem["is_online"] = False
            final_telem["is_roaming"] = is_roaming
            final_telem["roaming_routers"] = roaming_short_codes
            final_telem["roaming_label"] = "Offline"
            final_telem["status_label"] = "Offline"

        # Reconcile tethering detection across appearances
        any_sharing = any(t.get("is_sharing_hotspot") for _, t in appearances)
        sharing_t = next((t for _, t in appearances if t.get("is_sharing_hotspot")), None)
        final_telem["is_sharing_hotspot"] = any_sharing
        final_telem["sharing_timeout"] = sharing_t.get("sharing_timeout") if sharing_t else None
        final_telem["sharing_detail"] = sharing_t.get("sharing_detail") if sharing_t else None

        fleet_telemetry[mac] = final_telem

    _fleet_telemetry_cache = fleet_telemetry
    _fleet_telemetry_cache_time = now
    return fleet_telemetry


def broadcast_get_hotspot_sharing_suspects() -> List[Dict[str, Any]]:
    """
    Fetches all active hotspot sharing suspects from /ip/firewall/address-list across all active routers.
    """
    import database
    try:
        routers = database.get_all_routers(active_only=True)
    except Exception:
        routers = []

    if not routers:
        return []

    def _fetch_suspects(r):
        try:
            client = get_client_for_router(r)
            pool = routeros_api.RouterOsApiPool(
                client.host,
                username=client.username,
                password=client.password,
                port=client.port,
                use_ssl=client.use_ssl,
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()
            entries = api.get_resource('/ip/firewall/address-list').get(list='hotspot_sharing_suspects')
            pool.disconnect()
            r_name = r.get("name") or f"Router {r.get('id')}"
            short_code = get_router_short_code(r_name, r.get("id"))
            return [{
                "router_id": r.get("id"),
                "router_name": r_name,
                "router_short_code": short_code,
                "address": e.get("address"),
                "timeout": e.get("timeout"),
                "creation_time": e.get("creation-time"),
                "comment": e.get("comment", "")
            } for e in entries]
        except Exception as e:
            logger.debug(f"Could not fetch suspects from {r.get('name')}: {e}")
            return []

    with ThreadPoolExecutor(max_workers=len(routers) or 1) as executor:
        results = list(executor.map(_fetch_suspects, routers))

    all_suspects = []
    for res in results:
        all_suspects.extend(res)
    return all_suspects


def broadcast_get_online_mac_addresses(max_cache_age_sec: float = 4.0) -> List[str]:
    """
    Returns list of MAC addresses currently online across any router in the fleet.
    """
    tmap = broadcast_get_devices_telemetry_map(max_cache_age_sec=max_cache_age_sec)
    return [mac for mac, t in tmap.items() if t.get("state") == "online"]


def broadcast_bind_device(
    mac_address: str,
    ip_address: Optional[str] = None,
    comment: str = "",
    rate_limit: Optional[str] = None
) -> Dict[str, Any]:
    """
    Bypasses a device MAC across ALL active MikroTik routers in the fleet.
    Enables instant roaming between SSID 1 (VLAN 10), SSID 2 (VLAN 20), and SSID 3 (VLAN 30).
    """
    import database
    routers = database.get_all_routers(active_only=True)
    results = {}
    for r in routers:
        client = get_client_for_router(r)
        ok = client.bind_device(
            mac_address=mac_address,
            ip_address=ip_address,
            comment=comment,
            rate_limit=rate_limit
        )
        results[r["name"]] = ok
        logger.info(f"Fleet Bind: {mac_address} on {r['name']} ({r['host']}) -> {ok}")
    return results


def broadcast_unbind_device(
    mac_address: str,
    ip_address: Optional[str] = None
) -> Dict[str, Any]:
    """
    Revokes/unbinds a device MAC across ALL active MikroTik routers in the fleet.
    """
    import database
    routers = database.get_all_routers(active_only=True)
    results = {}
    for r in routers:
        client = get_client_for_router(r)
        ok = client.unbind_device(mac_address=mac_address, ip_address=ip_address)
        results[r["name"]] = ok
        logger.info(f"Fleet Unbind: {mac_address} on {r['name']} ({r['host']}) -> {ok}")
    return results


def broadcast_sync_customer_devices_speed(
    devices: List[Dict[str, Any]],
    rate_limit: Optional[str],
    comment: str = ""
) -> Dict[str, bool]:
    """
    Broadcasts and synchronizes speed limit queues across ALL active MikroTik routers in the fleet.
    """
    import database
    routers = database.get_all_routers(active_only=True)
    results = {}
    for r in routers:
        client = get_client_for_router(r)
        ok = client.sync_customer_devices_speed(
            devices=devices,
            rate_limit=rate_limit,
            comment=comment
        )
        results[r["name"]] = ok
        logger.info(f"Fleet Speed Sync: {len(devices)} device(s) on {r['name']} ({r['host']}) -> {ok}")
    return results


def broadcast_sync_package_profile(
    profile_name: str,
    rate_limit: Optional[str] = None,
    shared_users: int = 1,
    package_type: str = "hotspot"
) -> Dict[str, Any]:
    """
    Synchronizes a bandwidth rate limit profile across ALL active MikroTik routers.
    """
    import database
    routers = database.get_all_routers(active_only=True)
    results = {}
    for r in routers:
        client = get_client_for_router(r)
        ok = client.sync_package_profile(
            profile_name=profile_name,
            rate_limit=rate_limit,
            shared_users=shared_users,
            package_type=package_type
        )
        results[r["name"]] = ok
    return results


def broadcast_delete_package_profile(profile_name: str) -> Dict[str, Any]:
    """
    Deletes a package profile across ALL active MikroTik routers.
    """
    import database
    routers = database.get_all_routers(active_only=True)
    results = {}
    for r in routers:
        client = get_client_for_router(r)
        ok = client.delete_package_profile(profile_name=profile_name)
        results[r["name"]] = ok
    return results


def broadcast_sync_pppoe_secret(
    username: str,
    password: str,
    profile: Optional[str] = None,
    remote_ip: Optional[str] = None,
    local_ip: Optional[str] = None,
    rate_limit: Optional[str] = None,
    disabled: bool = False,
    comment: str = ""
) -> Dict[str, bool]:
    """
    Provisions or updates a PPPoE secret across ALL active MikroTik routers in the fleet.
    """
    import database
    routers = database.get_all_routers(active_only=True)
    results = {}
    for r in routers:
        client = get_client_for_router(r)
        ok = client.sync_pppoe_secret(
            username=username,
            password=password,
            profile=profile,
            remote_ip=remote_ip,
            local_ip=local_ip,
            rate_limit=rate_limit,
            disabled=disabled,
            comment=comment
        )
        results[r["name"]] = ok
        logger.info(f"Fleet PPPoE Sync: {username} on {r['name']} ({r['host']}) -> {ok}")
    return results


def broadcast_remove_pppoe_secret(username: str) -> Dict[str, bool]:
    """
    Removes a PPPoE secret and terminates active sessions across ALL active MikroTik routers.
    """
    import database
    routers = database.get_all_routers(active_only=True)
    results = {}
    for r in routers:
        client = get_client_for_router(r)
        ok = client.remove_pppoe_secret(username=username)
        results[r["name"]] = ok
        logger.info(f"Fleet PPPoE Remove: {username} on {r['name']} ({r['host']}) -> {ok}")
    return results


def broadcast_toggle_pppoe_secret(username: str, disabled: bool = True) -> Dict[str, bool]:
    """
    Enables or disables a PPPoE secret across ALL active MikroTik routers.
    If disabled=True, immediately terminates active session.
    """
    import database
    routers = database.get_all_routers(active_only=True)
    results = {}
    for r in routers:
        client = get_client_for_router(r)
        ok = client.toggle_pppoe_secret(username=username, disabled=disabled)
        results[r["name"]] = ok
        logger.info(f"Fleet PPPoE Toggle (disabled={disabled}): {username} on {r['name']} ({r['host']}) -> {ok}")
    return results


def broadcast_get_active_pppoe_sessions() -> Dict[str, Dict[str, Any]]:
    """
    Aggregates active PPPoE sessions across all active routers into a map of {username: session_data}.
    """
    import database
    routers = database.get_all_routers(active_only=True)
    all_sessions = {}
    for r in routers:
        client = get_client_for_router(r)
        sess_map = client.get_pppoe_sessions_map()
        for u_name, s_data in sess_map.items():
            s_data["router_name"] = r["name"]
            all_sessions[u_name] = s_data
    return all_sessions


def broadcast_disconnect_pppoe_session(username: str) -> Dict[str, bool]:
    """
    Terminates active PPPoE session for username across all active routers.
    """
    import database
    routers = database.get_all_routers(active_only=True)
    results = {}
    for r in routers:
        client = get_client_for_router(r)
        ok = client.disconnect_pppoe_session(username=username)
        results[r["name"]] = ok
    return results


def sync_all_to_new_router(router_id: int) -> Dict[str, Any]:
    """
    When a new MikroTik router is added to the fleet, provisions ALL existing
    approved customer devices, package speed profiles, and PPPoE subscriber secrets to it automatically.
    """
    import database
    r = database.get_router_by_id(router_id)
    if not r:
        return {"success": False, "error": "Router not found"}

    client = get_client_for_router(r)

    # 1. Sync all package profiles
    packages = database.get_packages()
    pkgs_synced = 0
    for p in packages:
        ok = client.sync_package_profile(
            profile_name=p["mikrotik_profile"],
            rate_limit=p["rate_limit"],
            shared_users=p["shared_users"],
            package_type=p["type"]
        )
        if ok:
            pkgs_synced += 1

    # 2. Sync all approved customer devices with static IP and effective speed queues
    approved_devices = database.get_approved_devices()
    devices_synced = 0
    for d in approved_devices:
        mac = d.get("mac_address")
        ip = d.get("ip_address")
        cust_name = d.get("customer_name") or "Subscriber"
        pkg_rate = d.get("effective_speed_limit") or d.get("speed_limit") or d.get("package_rate_limit")
        comm = f"Sub: {cust_name} ({d.get('package_name', '')})"
        ok = client.bind_device(
            mac_address=mac,
            ip_address=ip,
            comment=comm,
            rate_limit=pkg_rate
        )
        if ok:
            devices_synced += 1

    # 3. Sync all PPPoE subscriber credentials
    pppoe_customers = database.get_all_pppoe_customers()
    pppoe_synced = 0
    for pc in pppoe_customers:
        u_name = pc.get("pppoe_username") or pc.get("phone")
        p_word = pc.get("pppoe_password") or "cyber123"
        prof = pc.get("pppoe_profile") or "pppoe-profile-ether4"
        rem_ip = pc.get("pppoe_remote_ip") or None
        is_dis = (pc.get("status") == "suspended")
        eff_speed = pc.get("speed_limit") or pc.get("package_rate_limit")
        notes_str = f" [{pc['notes'].strip()}]" if pc.get("notes") and pc["notes"].strip() else ""
        comm = f"CyberNet PPPoE: {pc['phone']} - {pc['name']}{notes_str}"
        ok = client.sync_pppoe_secret(
            username=u_name,
            password=p_word,
            profile=prof,
            remote_ip=rem_ip,
            rate_limit=eff_speed,
            disabled=is_dis,
            comment=comm
        )
        if ok:
            pppoe_synced += 1

    return {
        "success": True,
        "router": r["name"],
        "packages_synced": pkgs_synced,
        "devices_synced": devices_synced,
        "pppoe_synced": pppoe_synced
    }


def broadcast_sync_all_approved_devices() -> Dict[str, Any]:
    """
    Synchronizes all approved customer devices and PPPoE subscribers to all active MikroTik routers.
    Guarantees instant connectivity without login prompts.
    """
    import database
    routers = database.get_all_routers(active_only=True)
    approved_devices = database.get_approved_devices()
    pppoe_customers = database.get_all_pppoe_customers()
    results = {}
    for r in routers:
        client = get_client_for_router(r)
        count = 0
        for d in approved_devices:
            mac = d.get("mac_address")
            if not mac:
                continue
            cust_name = d.get("customer_name") or "Subscriber"
            pkg_name = d.get("package_name") or ""
            comm = f"Sub: {cust_name} ({pkg_name})"
            pkg_rate = d.get("effective_speed_limit") or d.get("speed_limit") or d.get("package_rate_limit")
            ok = client.bind_device(
                mac_address=mac,
                ip_address=d.get("ip_address"),
                comment=comm,
                rate_limit=pkg_rate
            )
            if ok:
                count += 1

        pp_count = 0
        for pc in pppoe_customers:
            u_name = pc.get("pppoe_username") or pc.get("phone")
            p_word = pc.get("pppoe_password") or "cyber123"
            prof = pc.get("pppoe_profile") or "pppoe-profile-ether4"
            rem_ip = pc.get("pppoe_remote_ip") or None
            is_dis = (pc.get("status") == "suspended")
            eff_speed = pc.get("speed_limit") or pc.get("package_rate_limit")
            notes_str = f" [{pc['notes'].strip()}]" if pc.get("notes") and pc["notes"].strip() else ""
            comm = f"CyberNet PPPoE: {pc['phone']} - {pc['name']}{notes_str}"
            ok = client.sync_pppoe_secret(
                username=u_name,
                password=p_word,
                profile=prof,
                remote_ip=rem_ip,
                rate_limit=eff_speed,
                disabled=is_dis,
                comment=comm
            )
            if ok:
                pp_count += 1

        results[r["name"]] = {"devices": count, "pppoe": pp_count}
        logger.info(f"Fleet Sync: Synced {count} devices and {pp_count} PPPoE subscribers on {r['name']} ({r['host']})")
    return results



