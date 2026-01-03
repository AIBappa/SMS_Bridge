Cloudflare Tunnel for SMS Bridge

This folder contains a minimal, non-invasive setup to run a Cloudflare Tunnel (using `cloudflared`) to expose an internal SMS Bridge backend (either local Docker or a K3s service) to the internet securely.

## Bidirectional Communication Flow

This setup enables two-way communication between your local K3s instance and the Cloudflare Hono backend:

1.  **Inbound Traffic (CF Hono Backend -> Local K3s):**
    *   The Cloudflare Tunnel securely exposes your local `sms_receiver` service to the internet.
    *   Your Cloudflare Worker at `https://validation.new-username.workers.dev/` can send requests to the public tunnel hostname (e.g., `https://sms.example.com`).
    *   **Use Case 1 (Onboarding - GET Hash):** The Hono backend sends a `GET` request to `https://sms.example.com/onboard/register?mobile_number=...` to retrieve a hash for a new mobile number. The tunnel forwards this to your local `sms_server`. This is exactly how the local test app works, but over the internet.
    *   **Use Case 2 (Receiving SMS - POST Data):** After a user is onboarded, the backend can `POST` SMS data to `https://sms.example.com/sms/receive`.
    *   `cloudflared` receives this traffic and forwards it to the internal K3s service (`http://sms-receiver.sms-bridge.svc.cluster.local:8080`).

2.  **Outbound Traffic (Local K3s -> CF Hono Backend):**
    *   The `sms_server.py` application can make direct outbound HTTP requests to `https://validation.new-username.workers.dev/sms-gateway`.
    *   This does **not** go through the tunnel. It is a standard egress connection from your K3s cluster to the public internet.
    *   This is used for sending validated SMS data or status updates from your local instance back to the Cloudflare backend.
    *   The `CF_BACKEND_URL` in your `.env` should be set to this URL.

In summary:
- **Inbound**: Cloudflare Worker -> Tunnel -> Local K3s
- **Outbound**: Local K3s -> Direct HTTP -> Cloudflare Worker

Files included
- `docker-compose.yml` - example to run `cloudflared` as a container and mount tunnel credentials
- `config.yml` - example Cloudflared ingress rules mapping hostname to internal backend
- `run_tunnel.sh` - helper script to start/stop the tunnel using docker-compose
- `k3s-secrets.md` - notes for uploading credentials to K3s as a secret and running cloudflared as a pod

Important: This directory is standalone and will not change the existing repository code. It documents the steps you should follow and sample files to run a Cloudflare Tunnel for the SMS Bridge backend.

Prerequisites
- A Cloudflare account with a zone (domain) you control
- `cloudflared` or Docker installed (for container mode)
- Access to the zone API token or Cloudflare Teams to create a tunnel
- (Optional) `kubectl` access for K3s deployments

## Step-by-Step Setup Guide for K3s

Follow these steps to connect your Cloudflare Tunnel to your local K3s cluster.

### Step 1: Install and Authenticate the Connector

The easiest way to start is by using the command provided in your Cloudflare Zero Trust dashboard after creating a tunnel.

1.  In the Cloudflare dashboard, select your new tunnel and the correct operating system (Linux, Debian/Ubuntu).
2.  You will be given a single command that looks like `cloudflared service install <YOUR_TOKEN>`.
3.  Run this command on your Linux machine. It will:
    *   Install the `cloudflared` software as a system service.
    *   Create the necessary authentication file (`cert.pem`) in `/etc/cloudflared/`. This links the connector to your Cloudflare account.
    *  Note: Cloudflare also displays another one time run command like `cloudflare tunnel run --token <YOUR_TOKEN>`. However note that this command will not work if the authentication file `cert.pem` has not been installed as per command in step 2 noted above.
4. Check that the cloudflared tunnel is running using the following commands:
    # Check if the service is running
    sudo systemctl status cloudflared

    # Get more detailed status
    sudo systemctl is-active cloudflared

### Step 2: Configure the Tunnel's Routing

The connector is running, but it doesn't know what to expose yet. You must create a configuration file to define the routing rules.

1.  Create a configuration file at `/etc/cloudflared/config.yml`.
2.  Add the following content, replacing `sms-k3s.your-domain.com` with the public hostname you intend to use.

    ```yaml
    # /etc/cloudflared/config.yml
    ingress:
      # Rule 1: Route traffic for your public hostname to your internal K3s service.
      - hostname: sms-k3s.your-domain.com
        service: http://sms-receiver.sms-bridge.svc.cluster.local:8080
      
      # Rule 2: This is a required catch-all rule. It returns a 404 error
      # for any requests that don't match the hostname above.
      - service: http_status:404
    ```

### Step 3: Restart the Service and Verify

Restart the `cloudflared` service to apply your new `config.yml`.

```bash
# Restart the service
sudo systemctl restart cloudflared

# Check its status to ensure it's running correctly
sudo systemctl status cloudflared
```

### Step 4: Create the Public DNS Record

The final step is to link your public hostname to the tunnel in Cloudflare's DNS.

1.  Go to your Cloudflare DNS dashboard for your domain.
2.  Create a `CNAME` record with the following details:
    *   **Type:** `CNAME`
    *   **Name:** `sms-k3s` (or the subdomain part of your hostname)
    *   **Target:** `<YOUR_TUNNEL_ID>.cfargotunnel.com` (You can find your Tunnel ID in the Cloudflare dashboard).
    *   **Proxy status:** Proxied (Orange Cloud).

After these steps, any request to `https://sms-k3s.your-domain.com` will be securely routed through the tunnel to your local K3s `sms-receiver` service.

Security notes
- Keep `credentials-file.json` private (do not commit)
- Use Cloudflare Access policies if you need authentication in front of the tunnel
- Use short-lived or scoped API tokens when possible

See other files for detailed instructions and examples.

This updated guide should provide the clarity you need to get the tunnel up and running successfully. The API token you have is generally used for automating Cloudflare actions via scripts, but for this manual setup, the auto-generated installation command is all you need.