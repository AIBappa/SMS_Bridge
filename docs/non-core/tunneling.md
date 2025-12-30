This is a short and sweet document because the Tunneling aspect keeps on coming into the picture often.

The current app is using the CF tunnel.

There are 2 method to setup a tunnel.
1) Using bash command directly and all config files reside on local machine.
2) Using Cloudflare dashboard – following commands from Zero Trust → Networks → Connectors. This shows the Tunnel dashboard.

The current tunnel has been setup using second method.

Using this method, cloudflared tunnel is running as a service on the local machine which is a Linux BOSS version.
The status can be checked using the following command.

> sudo systemctl status cloudflared

This command will inform is the cloudflared service is running on laptop.

On CF dashboard, there are different “Published Application Routes” that can be used to add a new API call through the same tunnel. Note that it is preferable to run one tunnel on one machine and all different API calls can be routed via the same tunnel. 

These API calls can come from client devices (webapp on CF Hono TS) routed towards local device as endpoint as well as call sourced from local device towards endpoint server like Hetzner.

All of these calls can be inside the single tunnel as defined on the CF dashboard.

Have to check Coolify Dashboard on Hetzner.
46.62.208.29:8000 -use this
