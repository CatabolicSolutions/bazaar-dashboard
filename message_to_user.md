I have completed the code modifications in `dashboard/scripts/serve_dashboard.py` to address the "deployable capital number" issue. The dashboard should now fetch real-time wallet balances directly from the API via `wallet_monitor.get_all_balances()` instead of relying on potentially stale local state files.

**For the changes to take effect, the `bazaar-dashboard.service` needs to be restarted.** Due to `sudo` requiring a password, I cannot perform this action directly. Please restart the service manually by running the following command in your terminal:

```bash
sudo systemctl restart bazaar-dashboard.service
```

After restarting the service, please verify the following:

1.  **"Deployable Capital Number"**: Check the dashboard UI to ensure that the "deployable capital number" (and any related balance displays in `/api/eth-scalper/status` or `/api/hq/status` endpoints) accurately reflects the real-time balances. You can manually compare this with your actual wallet balances from a blockchain explorer or other trusted sources.
2.  **`/api/eth-scalper/wallet` Endpoint**: Ensure this endpoint continues to function correctly and returns accurate, real-time balances.

**Regarding the "hosted site" issue:**

I have confirmed that the `serve_dashboard.py` script binds to `0.0.0.0` by default, which means it is configured to be accessible from all network interfaces (i.e., not just LAN). The presence of `cloudflare_tunnel.log` and `cloudflare_tunnel.pid` also indicates an attempt to expose the service publicly.

If you are still experiencing issues where the dashboard "feels like it's on LAN" or is not reliably accessible via your desired "hosted site" experience (e.g., via a custom domain name), this would likely stem from external configurations beyond the codebase:

*   **Cloudflare Tunnel Configuration**: Double-check your Cloudflare Tunnel setup to ensure it's correctly forwarding traffic to the dashboard.
*   **DNS Configuration**: If you expect to access it via a domain name, ensure your DNS records are correctly pointing to your server's public IP and that Cloudflare (or any other proxy) is configured properly.
*   **Server/Network Stability**: The underlying server or network connection might have intermittent issues.

My changes address the data inaccuracy. Any further issues related to "hosting" would require investigation of your specific deployment environment and external network services.
