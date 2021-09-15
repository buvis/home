# Update wg0.conf
1. Edit wg0.conf
2. Encode it to base64: `base64 wg0.conf`
3. Open cluster-secrets.yaml: `sops ~/clusters/buvis-prod/flux-system/extras/cluster-secrets.yaml`
4. Replace SECRET_WIREGUARD_WG0_CONF key by content from step 2
