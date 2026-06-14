# Networking

Services bind to `0.0.0.0` by default so they are reachable on the LAN.

| Service | Port |
| --- | ---: |
| `eliza-medium` | `8001` |
| `eliza-small` | `8002` |
| `stt` | `8011` |
| `tts` | `8012` |
| `vocode-bridge` | `8021` |

These endpoints do not enforce authentication by default. Keep them on a trusted LAN, or add firewall rules, VPN access, or an authenticated reverse proxy before exposing them outside your network.

Local test URLs:

```bash
curl http://127.0.0.1:8001/v1/models
curl http://127.0.0.1:8002/v1/models
curl http://127.0.0.1:8011/v1/models
curl http://127.0.0.1:8012/v1/models
curl http://127.0.0.1:8021/health
```

LAN clients should use the DGX Spark host IP, for example:

```text
http://192.168.1.50:8001/v1
http://192.168.1.50:8002/v1
http://192.168.1.50:8011/v1
http://192.168.1.50:8012/v1
ws://192.168.1.50:8021/ws
```

OpenAI-style audio endpoints:

```text
POST http://192.168.1.50:8011/v1/audio/transcriptions
POST http://192.168.1.50:8012/v1/audio/speech
```

Vocode bridge endpoint:

```text
WS ws://192.168.1.50:8021/ws
```
