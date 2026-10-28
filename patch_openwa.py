import subprocess
import sys

def run(cmd):
    print(f">> {cmd}")
    res = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if res.stdout:
        print(res.stdout)
    if res.stderr:
        print(res.stderr)
    return res.returncode

def patch():
    # 1. Copy files from container
    run("docker cp openwa:/app/dist/engine/adapters/whatsapp-web-js.adapter.js /tmp/adapter.js")
    run("docker cp openwa:/app/node_modules/whatsapp-web.js/src/util/Injected/Utils.js /tmp/Utils.js")

    # 2. Patch adapter.js
    with open("/tmp/adapter.js", "r", encoding="utf-8") as f:
        adapter = f.read()

    # In sendTextMessage:
    old_send_text = """    async sendTextMessage(chatId, text) {
        this.ensureReady();
        const msg = await this.client.sendMessage(chatId, text);
        return {
            id: msg.id._serialized,
            timestamp: msg.timestamp,
        };
    }"""

    new_send_text = """    async sendTextMessage(chatId, text) {
        this.ensureReady();
        const msg = await this.client.sendMessage(chatId, text);
        return {
            id: (msg && msg.id && msg.id._serialized) || (msg && msg.id) || ('txt_' + Date.now()),
            timestamp: (msg && msg.timestamp) || Math.floor(Date.now() / 1000),
        };
    }"""

    old_send_media = """        const msg = await this.client.sendMessage(chatId, messageMedia, {
            caption: media.caption,
            sendMediaAsDocument: true,
        });
        return {
            id: (msg && msg.id && msg.id._serialized) || (msg && msg.id) || ('doc_' + Date.now()),
            timestamp: (msg && msg.timestamp) || Math.floor(Date.now() / 1000),
        };"""

    old_from_url = "messageMedia = await whatsapp_web_js_1.MessageMedia.fromUrl(media.data);"
    new_from_url = "messageMedia = await whatsapp_web_js_1.MessageMedia.fromUrl(media.data, { unsafeMime: true, filename: media.filename });"

    adapter = adapter.replace(old_from_url, new_from_url)
    with open("/tmp/adapter.js", "w", encoding="utf-8") as f:
        f.write(adapter)
    print("adapter.js patched successfully.")

    # 3. Patch Utils.js
    with open("/tmp/Utils.js", "r", encoding="utf-8") as f:
        utils = f.read()

    old_msg_create = """        const message = {
            ...options,
            id: newMsgKey,
            ack: 0,
            body: content,
            from: from,
            to: chat.id,
            local: true,
            self: 'out',
            t: parseInt(new Date().getTime() / 1000),
            isNewMsg: true,
            type: 'chat',
            ...ephemeralFields,
            ...mediaOptions,
            ...(mediaOptions.toJSON ? mediaOptions.toJSON() : {}),
            ...quotedMsgOptions,
            ...locationOptions,
            ...pollOptions,
            ...eventOptions,
            ...vcardOptions,
            ...buttonOptions,
            ...listOptions,
            ...botOptions,
            ...extraOptions,
        };"""

    new_msg_create = """        if (mediaOptions) {
            delete mediaOptions.__x_id;
            delete mediaOptions.id;
        }
        const message = {
            ...options,
            id: newMsgKey,
            ack: 0,
            body: content,
            from: from,
            to: chat.id,
            local: true,
            self: 'out',
            t: parseInt(new Date().getTime() / 1000),
            isNewMsg: true,
            type: 'chat',
            ...ephemeralFields,
            ...mediaOptions,
            ...(mediaOptions.toJSON ? mediaOptions.toJSON() : {}),
            ...quotedMsgOptions,
            ...locationOptions,
            ...pollOptions,
            ...eventOptions,
            ...vcardOptions,
            ...buttonOptions,
            ...listOptions,
            ...botOptions,
            ...extraOptions,
        };
        message.id = newMsgKey;"""

    old_msg_return = """        return window
            .require('WAWebCollections')
            .Msg.get(newMsgKey._serialized);"""

    new_msg_return = """        return window
            .require('WAWebCollections')
            .Msg.get(newMsgKey._serialized) || (chat.msgs && chat.msgs.last && chat.msgs.last());"""

    if old_msg_create not in utils or old_msg_return not in utils:
        print("ERROR: old patterns not found in Utils.js")
        return False

    utils = utils.replace(old_msg_create, new_msg_create).replace(old_msg_return, new_msg_return)
    with open("/tmp/Utils.js", "w", encoding="utf-8") as f:
        f.write(utils)
    print("Utils.js patched successfully.")

    # 4. Copy back into container
    run("docker cp /tmp/adapter.js openwa:/app/dist/engine/adapters/whatsapp-web-js.adapter.js")
    run("docker cp /tmp/Utils.js openwa:/app/node_modules/whatsapp-web.js/src/util/Injected/Utils.js")

    # 5. Restart container
    print("Restarting openwa container...")
    run("docker restart openwa")
    return True

if __name__ == "__main__":
    patch()
