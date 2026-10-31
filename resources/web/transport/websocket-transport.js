// WebSocket transport: thin wrapper over the existing ws:// connection to the
// C++ wfweb server. Behaviour matches the pre-refactor inline ws code in
// index.html exactly — same URL derivation, same JSON envelope, same binary
// frame format.

(function (global) {
    'use strict';

    function defaultUrlBuilder() {
        // BARC-hosted UI connects to its own origin; the Raspberry Pi makes
        // the outbound station connection. Never expose the Pi to browsers.
        var node = location.pathname.match(/^\/radio\/([a-z0-9-]+)\/nodes\/([a-z0-9-]+)\//);
        if (node) {
            return (location.protocol === 'https:' ? 'wss://' : 'ws://') +
                location.host + '/ws/radio/' + node[1] + '/' + node[2];
        }
        var station = location.pathname.match(/^\/radio\/([a-z0-9-]+)\//);
        if (station) {
            return (location.protocol === 'https:' ? 'wss://' : 'ws://') +
                location.host + '/ws/radio/' + station[1];
        }
        if (location.protocol === 'https:') {
            return 'wss://' + location.hostname + ':' + (location.port || '443');
        }
        var port = parseInt(location.port || '80') + 1;
        return 'ws://' + location.hostname + ':' + port;
    }

    class WebSocketRigTransport extends global.RigTransport {
        constructor(opts) {
            super();
            opts = opts || {};
            this.urlBuilder = opts.urlBuilder || defaultUrlBuilder;
            this.ws = null;
            this.barc = /^\/radio\//.test(location.pathname);
            this.operator = !this.barc;
            if (this.barc) {
                document.body.classList.add('barc-relay');
                ['powerBtn','powerOnBtn','lanConnBtn'].forEach(function(id) {
                    var button = document.getElementById(id);
                    if (button) {
                        button.disabled = true;
                        button.title = 'Power and LAN connection controls are unavailable in BARC Remote.';
                    }
                });
            }
        }

        connect() {
            if (this.barc) {
                this.operator = false;
                this.showBarcStatus('BARC · Connecting to station. Listen-only until a reservation is verified.');
            }
            if (this.ws) {
                try { this.ws.close(); } catch (e) { /* ignore */ }
                this.ws = null;
            }
            var url = this.urlBuilder();
            var ws = new WebSocket(url);
            ws.binaryType = 'arraybuffer';
            var self = this;
            ws.onopen    = function ()  { self.dispatchEvent(new Event('open')); };
            ws.onclose   = function (e) {
                if (self.barc) {
                    self.operator = false;
                    self.showBarcStatus('BARC · Station connection closed. Control and transmit are unavailable.');
                }
                self.dispatchEvent(new CustomEvent('close', { detail: e }));
            };
            ws.onerror   = function (e) { self.dispatchEvent(new CustomEvent('error', { detail: e })); };
            ws.onmessage = function (event) {
                if (event.data instanceof ArrayBuffer) {
                    self.dispatchEvent(new CustomEvent('binary', { detail: event.data }));
                    return;
                }
                try {
                    var msg = JSON.parse(event.data);
                    if (msg.type === 'barcPermission' || msg.type === 'barcDenied') {
                        if (msg.type === 'barcPermission') self.operator = msg.operator === true;
                        self.showBarcStatus(msg.type === 'barcDenied' ? msg.reason :
                            self.operator ? 'BARC · Your reservation is active. Radio control enabled.' :
                            'BARC · Listen only. Radio control requires your active reservation. Book at remote.barc.ca/bookings.');
                        return;
                    }
                    self.dispatchEvent(new CustomEvent('message', { detail: msg }));
                } catch (err) {
                    console.error('WebSocketRigTransport parse error:', err);
                }
            };
            this.ws = ws;
        }

        showBarcStatus(text) {
            var banner = document.getElementById('barc-access-banner');
            if (!banner) {
                banner = document.createElement('div');
                banner.id = 'barc-access-banner';
                banner.setAttribute('role', 'status');
                document.body.prepend(banner);
            }
            banner.textContent = text;
            banner.className = this.operator ? 'barc-operator' : 'barc-listener';
        }

        close() {
            if (this.ws) {
                try { this.ws.close(); } catch (e) { /* ignore */ }
                this.ws = null;
            }
        }

        isOpen() {
            return !!(this.ws && this.ws.readyState === WebSocket.OPEN);
        }

        sendCommand(obj) {
            if (this.barc && ['setPower','reconnectLan','disconnectLan'].indexOf(obj.cmd) !== -1) {
                this.showBarcStatus('BARC · Power and LAN connection controls are unavailable in this console.');
                return false;
            }
            if (this.barc && !this.operator && obj.cmd !== 'getStatus' && obj.cmd !== 'enableAudio') {
                this.showBarcStatus('BARC · Listen only: tuning and transmit require an active reservation. Check your slot at remote.barc.ca/bookings.');
                return false;
            }
            if (this.isOpen()) this.ws.send(JSON.stringify(obj));
        }

        sendAudioFrame(buffer) {
            if (this.barc && !this.operator) return;
            if (this.isOpen()) this.ws.send(buffer);
        }
    }

    global.WebSocketRigTransport = WebSocketRigTransport;
})(window);
