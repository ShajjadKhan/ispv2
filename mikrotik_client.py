"""
MikroTik RouterOS API Client for CyberNet v2.
Handles live connectivity checks, system resource metrics, interface states, and latency.
"""

import time
import re
import logging
from typing import List, Dict, Any, Optional, Union
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

class RouterClient:
    def __init__(
        self,
        host: str = "10.20.30.1",
        username: str = "admin",
        password: str = "admin",
        port: int = 8728,
        use_ssl: bool = False
    ):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.use_ssl = use_ssl

    def get_live_status(self) -> Dict[str, Any]:
        """
        Connects to MikroTik and fetches live status, resource metrics, and interfaces.
        Returns a structured dictionary with success state, latency, and hardware telemetry.
        """
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

            # 4. Interfaces
            ifaces_raw = api.get_resource('/interface').get()
            interfaces = []
            for i in ifaces_raw:
                interfaces.append({
                    "name": i.get("name"),
                    "type": i.get("type"),
                    "running": i.get("running") == "true",
                    "disabled": i.get("disabled") == "true",
                    "comment": i.get("comment", "")
                })

            # 5. IP Addresses
            ip_list = api.get_resource('/ip/address').get()
            ip_map = {}
            for ip in ip_list:
                iface = ip.get("interface")
                addr = ip.get("address")
                if iface and addr:
                    ip_map[iface] = addr

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

            return {
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
                "ip_map": ip_map,
                "error": None,
                "checked_at": time.strftime("%H:%M:%S")
            }
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
                "ip_map": {},
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
            found_id = None
            for b in existing_bindings:
                if b.get('mac-address', '').upper() == mac_clean:
                    found_id = b['id']
                    break

            if found_id:
                binding_res.set(id=found_id, type='bypassed', comment=comment)
                logger.info(f"Updated existing IP binding for MAC {mac_clean} to bypassed.")
            else:
                add_kwargs = {'mac-address': mac_clean, 'type': 'bypassed', 'comment': comment}
                if ip_address:
                    add_kwargs['address'] = ip_address
                binding_res.add(**add_kwargs)
                logger.info(f"Created new IP binding for MAC {mac_clean} as bypassed.")

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
                    target_ip = ip_address
                    if not target_ip:
                        for h in api.get_resource('/ip/hotspot/host').get():
                            if h.get('mac-address', '').upper() == mac_clean and h.get('address'):
                                target_ip = h.get('address')
                                break
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

            # 1. Discover client IP(s)
            client_ips = []
            if ip_address:
                client_ips.append(ip_address)

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

            # 2. Remove from /ip/hotspot/ip-binding
            binding_res = api.get_resource('/ip/hotspot/ip-binding')
            for b in binding_res.get():
                if b.get('mac-address', '').upper() == mac_clean:
                    binding_res.remove(id=b['id'])
                    logger.info(f"Removed IP binding for {mac_clean}")

            # 3. Remove from /ip/hotspot/active
            try:
                active_res = api.get_resource('/ip/hotspot/active')
                for a in active_res.get():
                    if a.get('mac-address', '').upper() == mac_clean:
                        active_res.remove(id=a['id'])
                        logger.info(f"Removed active session for {mac_clean}")
            except Exception:
                pass

            # 4. Remove from /ip/hotspot/cookie
            try:
                cookie_res = api.get_resource('/ip/hotspot/cookie')
                for c in cookie_res.get():
                    if c.get('mac-address', '').upper() == mac_clean:
                        cookie_res.remove(id=c['id'])
            except Exception:
                pass

            # 5. Flush active TCP/UDP connections in firewall conntrack
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

            # 6. Remove simple queue if any
            try:
                queue_res = api.get_resource('/queue/simple')
                q_name = f"hs-{mac_clean.replace(':', '')}"
                for q in queue_res.get():
                    if q.get('name') == q_name:
                        queue_res.remove(id=q['id'])
            except Exception:
                pass

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
                    "rate-limit": effective_rate
                }
                if existing:
                    res.set(id=existing[0]["id"], **params)
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

    def get_online_mac_addresses(self) -> List[str]:
        """
        Fetches all MAC addresses currently active in /ip/hotspot/host and bound in /ip/dhcp-server/lease.
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

            return list(active_macs)
        except Exception as e:
            logger.warning(f"Could not fetch online MAC addresses from MikroTik: {e}")
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
    try:
        pool = routeros_api.RouterOsApiPool(
            host,
            username=username,
            password=password,
            port=port,
            use_ssl=False,
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
    return RouterClient(
        host=r_dict["host"],
        username=r_dict["username"],
        password=r_dict["password"],
        port=r_dict.get("port", 8728)
    )


def broadcast_bind_device(
    mac_address: str,
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
        ok = client.bind_device(mac_address=mac_address, comment=comment, rate_limit=rate_limit)
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


def sync_all_to_new_router(router_id: int) -> Dict[str, Any]:
    """
    When a new MikroTik router is added to the fleet, provisions ALL existing
    approved customer devices and package speed profiles to it automatically.
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

    # 2. Sync all approved customer devices
    approved_devices = database.get_approved_devices()
    devices_synced = 0
    for d in approved_devices:
        mac = d.get("mac_address")
        cust_name = d.get("customer_name") or "Subscriber"
        pkg_rate = d.get("package_rate_limit")
        comm = f"Sub: {cust_name} ({d.get('package_name', '')})"
        ok = client.bind_device(mac_address=mac, comment=comm, rate_limit=pkg_rate)
        if ok:
            devices_synced += 1

    return {
        "success": True,
        "router": r["name"],
        "packages_synced": pkgs_synced,
        "devices_synced": devices_synced
    }



