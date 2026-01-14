# SMS Bridge Monitoring Specification v2.3

**Simple Version - Requirements Only (No Code)**

This document explains what monitoring features SMS Bridge needs, written in plain language that anyone can understand.

> 💡 **For developers**: See `SMS_Bridge_monitoring_snippets_v2.3.md` for all code examples and technical implementation details.

---

## 1. What is This Document About?

**The Big Idea**: Instead of running heavy monitoring tools on our server all the time, we only turn them on when we need to check how things are working. It's like turning on a flashlight only when you need to see in the dark, rather than leaving it on 24/7.

### How It Works

**Server (Surface Pro):**
- Runs the main SMS Bridge app
- Keeps small log files (like a diary of what happened)
- Has special "doors" (ports) that are normally closed
- Admin can open these "doors" temporarily when they need to check something

**Laptop (Your Computer):**
- Has monitoring tools (like a dashboard with graphs)
- Only runs when you want to check on things
- Connects to server through temporarily opened "doors"
- Shows pretty graphs and data about how the server is doing

### Why This Way is Better

✅ **Saves Resources**: Server doesn't waste memory running tools we rarely use  
✅ **More Secure**: "Doors" (ports) only open when needed, not all the time  
✅ **Flexible**: Can check monitoring from any laptop, anywhere  
✅ **Simpler**: Less stuff running means less stuff that can break  

### What You Save

**Old Way** (v2.2 - everything on server):
- Used ~900MB of server memory
- Used ~2GB of server disk space
- Had 8 containers running
- Had 3 ports exposed to internet

**New Way** (v2.3 - minimal server):
- Uses ~350MB of server memory (60% less!)
- Uses ~100MB of server disk space (95% less!)
- Has 4 containers running
- Has only 1 port exposed to internet

---

## 2. Logging (Keep a Diary of What Happens)

### What is Logging?

Logging is like keeping a diary of what happens on your server. But instead of writing everything, we only write down important stuff (errors and warnings).

### What Gets Written Down

**Always Logged (Security Events):**
- When someone logs into admin panel
- When someone opens a monitoring port
- When someone closes a monitoring port
- When someone changes settings
- When someone adds/removes from blacklist

**Sometimes Logged (Problems):**
- When things go wrong (errors)
- When things might go wrong soon (warnings)
- When someone tries too many times (rate limiting)
- When validation checks fail

**Never Logged (Too Much Noise):**
- Successful requests (we use metrics for this instead)
- Debug information (only needed during development)
- Routine operations (things that happen normally)

### How Long Do We Keep Logs?

- **7 days** - After that, old logs are deleted automatically
- **10MB per file** - When a log file gets too big, it rotates (creates a new file)
- **~100MB total** - All logs combined take up about 100MB of disk space

### Where Are Logs Stored?

Logs are saved on the host machine (not inside containers), so they survive even if you restart the containers:
- Application logs: `./logs/application/sms_bridge.log`
- PostgreSQL logs: `./logs/postgres/postgresql-YYYY-MM-DD.log`
- Redis logs: `./logs/redis/redis.log`
- Port access audit: `/app/logs/port_mappings.json`

### How Can Admin See Logs?

Admin can:
1. View recent logs in the web browser (Admin UI)
2. Download log files to their computer
3. Filter logs by service (application, database, cache)
4. See who opened which ports and when

---

## 3. Port Management (Opening and Closing "Doors")

### What are Ports?

Think of ports like doors on a building. Normally, all doors are locked. When you need to let someone in, you open a specific door, they come in, and then you lock it again.

### Which "Doors" Can Be Opened?

| Service | What It's For | Default Port Number |
|---------|---------------|---------------------|
| **Metrics** | Let Prometheus collect data | 9100 |
| **PostgreSQL** | Let DBeaver connect to database | 5433 |
| **PgBouncer** | Database connection pooler | 6434 |
| **Redis** | Let Redis Desktop Manager connect to cache | 6380 |

### How to Open a Port

**Step-by-Step:**
1. Admin logs into Admin UI (https://your-domain.com/admin)
2. Goes to "Monitoring Services" page
3. Clicks on the service they want (e.g., "PostgreSQL")
4. Chooses how long to keep it open (15 minutes to 4 hours)
5. Clicks "Open Port"
6. System gives you connection details (IP address, port number, password)
7. Port automatically closes after the time you chose

### Security Features

**Who Can Open Ports?**
- Only admins who are logged in
- Every action is recorded (who, what, when)

**How Long Do Ports Stay Open?**
- Minimum: 15 minutes
- Maximum: 4 hours
- Default: 1 hour
- Automatically closes after time expires

**What Gets Recorded?**
- Who opened the port
- When it was opened
- How long it was open for
- When it was closed (automatically or manually)
- Which computer connected

### Customizing Port Numbers

**Why Customize?**
Sometimes the default port numbers conflict with other services, or you want to use different numbers for security reasons.

**How It Works:**
1. Port numbers are stored in `sms_settings.json` (same file as other settings)
2. Admin can change port numbers through Admin UI
3. Changes take effect immediately (no restart needed)
4. Must close all open ports before changing numbers

**Rules for Port Numbers:**
- Must be between 1024 and 65535
- Each service must have a unique port number
- Port must not be used by another program
- Changes are logged for security

**What Happens When You Change Ports:**
1. System checks if any ports are currently open (must close them first)
2. Admin enters new port numbers in Admin UI
3. System validates (checks if ports are available)
4. System saves to `sms_settings.json`
5. Next time you open a port, it uses the new number
6. You need to update your laptop's configuration too

---

## 4. Metrics (Numbers That Show How Things Are Going)

### What are Metrics?

Metrics are numbers that tell you how your system is performing. It's like checking your car's dashboard - speed, fuel, temperature, etc.

### What Metrics Do We Track?

**Counters (Things That Go Up):**
- How many onboarding requests (successful and failed)
- How many SMS messages received
- How many PINs collected
- How many requests were rate-limited
- How many validation checks failed

**Gauges (Current Snapshot):**
- How many items waiting to sync
- How many items in audit buffer
- How many numbers are blacklisted
- How many onboardings are active right now
- How many verified users waiting for PIN

### Where Do Metrics Come From?

- Server constantly updates these numbers
- Available at `http://your-server:8080/metrics`
- Prometheus scrapes (collects) them every 15 seconds
- Grafana turns them into pretty graphs

### How to View Metrics?

**Simple Way (Text):**
- Visit `http://your-server:8080/metrics` in browser
- See all metrics as plain text
- Good for quick checks

**Better Way (Graphs):**
1. Open monitoring ports on server
2. Start Grafana on laptop
3. View beautiful dashboards with graphs
4. See trends over time (last hour, day, week)

---

## 5. Monitoring from Your Laptop

### What Do You Need?

**On Server (Surface Pro):**
- SMS Bridge running (always on)
- Ports closed (normal state)

**On Laptop:**
- Docker installed
- Monitoring configuration files
- About 500MB of free RAM
- About 2GB of free disk space

### Step-by-Step: Start Monitoring

**1. (Optional) Configure Ports**
- If default ports don't work, change them in Admin UI
- Only needed first time or if there's a conflict

**2. Open Ports on Server**
```
Visit: https://your-domain.com/admin/monitoring/services
Click: "Open All Monitoring Ports"
Choose: 60 minutes
Result: System shows connection details for each service
```

**3. Start Monitoring on Laptop**
```
Open terminal
Go to monitoring folder
Run: ./start-monitoring.sh your-server-ip
Wait: 15-30 seconds
Open browser: http://localhost:3000 (Grafana)
```

**4. View Dashboards**
- Grafana shows pretty graphs
- See real-time metrics
- Check historical data (up to 7 days)

**5. Connect Tools (Optional)**
- DBeaver for database: Connect to your-server-ip:5433
- Redis Desktop Manager: Connect to your-server-ip:6380

**6. Done? Stop Monitoring**
```
Close laptop monitoring: ./stop-monitoring.sh
Close server ports: Admin UI → "Close All Ports"
```

### Helper Scripts

We provide simple scripts to make it easy:

**start-monitoring.sh**
- Sets up everything automatically
- Starts Prometheus and Grafana
- Opens browser to dashboards

**stop-monitoring.sh**
- Stops all monitoring containers
- Cleans up resources

**check-monitoring.sh**
- Shows what's running
- Checks if everything is healthy

---

## 6. Dashboards (Pretty Graphs)

### What Can You See?

**SMS Bridge Overview Dashboard:**
1. **Request Rate** - How many requests per minute
2. **SMS Processing** - How fast we're processing messages
3. **PIN Collection** - How many PINs collected
4. **Validation Failures** - Which checks are failing
5. **Queue Depths** - How many items waiting
6. **Active Sessions** - Current ongoing operations
7. **Blacklist Size** - How many numbers blocked
8. **Rate Limiting** - Are we blocking too many requests?

**Data Tables Dashboard:**
1. **Recent Logs** - Last 50 log entries
2. **Backup Users** - Users pending sync
3. **Settings History** - When settings were changed
4. **Blacklist** - Recently blocked numbers

### How to Read Graphs?

- **Line going up** = More activity
- **Line going down** = Less activity
- **Spikes** = Sudden burst of activity
- **Flat line** = Stable/no change
- **Different colors** = Different categories (success vs failed)

---

## 7. Security

### How is This Secure?

**Authentication:**
- Must login to Admin UI to open ports
- Session expires after inactivity
- Password is hashed (encrypted)

**Time Limits:**
- Ports close automatically
- Maximum 4 hours
- Can't leave them open forever

**Audit Trail:**
- Everything is logged
- Can see who did what and when
- Helps catch unauthorized access

**Network Security:**
- Main app behind Cloudflare (DDoS protection)
- Monitoring ports NOT behind Cloudflare (direct access only)
- Only 1 port exposed normally (8080)

### Best Practices

**Port Numbers:**
- Change default ports after first deployment
- Use non-obvious numbers (not 5432, use 5433 or random)
- Document changes in secure location
- Rotate ports every 6 months

**Access:**
- Only give admin access to trusted people
- Use strong passwords
- Monitor audit trail regularly
- Close ports when done (don't leave open)

### Threat Model (What Could Go Wrong?)

**Possible Attacks:**
- Attacker scans for open ports
- Brute force tries to guess passwords
- Unauthorized access to monitoring data

**How We Prevent:**
- Ports only open when you explicitly open them
- Strong password requirements
- Rate limiting on login attempts
- Everything logged
- Auto-close prevents forgotten open ports

---

## 8. Troubleshooting

### Problem: Can't See Metrics in Grafana

**Check:**
1. Is monitoring port open on server? (Check Admin UI)
2. Is server IP correct in config file?
3. Can you access metrics directly? Try: `curl http://server-ip:port/metrics`
4. Is Prometheus running on laptop? Run: `docker ps`
5. Did port numbers change? Re-download config from Admin UI

### Problem: DBeaver Won't Connect to Database

**Check:**
1. Is PostgreSQL port open? (Check Admin UI → Port Status)
2. Is password correct? (Check .env file)
3. Is SSL mode set to "disable" in DBeaver?
4. Try command line first: `psql "postgresql://user:pass@server:5433/db"`
5. Is pgbouncer healthy? Check with: `docker ps`

### Problem: Can't Open Port

**Error: "Failed to configure firewall"**

**Check:**
1. Is iptables installed on server?
2. Does container have permission? (May need special settings)
3. Check server logs: `docker logs sms_receiver`
4. Try manual check: `sudo iptables -L -n`

**Backup Plan:**
Use SSH tunnel instead:
```
ssh -L 5433:localhost:5432 user@server  (for database)
ssh -L 6380:localhost:6379 user@server  (for redis)
```

### Problem: Logs Disappear After Restart

**Check:**
1. Are volumes mounted correctly? `docker inspect sms_receiver`
2. Do log folders exist? `ls -la ./logs/`
3. Are permissions correct? `ls -la ./logs/application/`
4. Check docker-compose file has volume mounts

### Problem: Port Configuration Won't Save

**Error: "Port in use"**

**Solution:**
1. Find what's using the port: `sudo lsof -i :9100`
2. Kill that process (if safe): `sudo kill -9 PID`
3. Or choose a different port number
4. Use "Scan Available Ports" button in Admin UI

**Error: "Port currently open"**

**Solution:**
1. Close all open monitoring ports first
2. Then change port configuration
3. System prevents changing while ports are open for safety

---

## 9. Migrating from Old Version

### If You're Running v2.2 (Full Stack on Server)

**What to Remove:**
- Prometheus container on server
- Grafana container on server
- postgres_exporter container
- redis_exporter container

**What to Keep:**
- SMS Bridge (sms_receiver)
- PostgreSQL
- PgBouncer
- Redis

**Steps:**
1. **Backup First!** Export Grafana dashboards, save Prometheus data
2. **Stop old containers**: `docker-compose down prometheus grafana postgres_exporter redis_exporter`
3. **Remove old volumes** (optional): `docker volume rm prometheus_data grafana_data`
4. **Update docker-compose.yml** to new format (v2.3)
5. **Add monitoring ports to sms_settings.json**
6. **Deploy updated version**
7. **Test port opening/closing**
8. **Setup laptop monitoring**

### Testing Migration

Before doing this in production:
1. Test in development/staging environment first
2. Make sure port opening works
3. Test laptop monitoring can connect
4. Verify logs are persisting
5. Check external tools (DBeaver, Redis Manager) can connect
6. Do a load test with ports open

---

## 10. Deployment Checklist

### Server Setup (Do Once)

- [ ] SMS Bridge app deployed
- [ ] Admin UI working
- [ ] Port management endpoints added
- [ ] Port configuration page in Admin UI
- [ ] Default monitoring ports in sms_settings.json
- [ ] Port validation working
- [ ] Minimal logging configured (WARNING level)
- [ ] Log rotation enabled (7 days)
- [ ] Log folders mounted properly
- [ ] Audit trail for ports enabled
- [ ] Cloudflare Tunnel set up
- [ ] Environment variables set (passwords, secrets)
- [ ] NO monitoring containers on server
- [ ] ONLY port 8080 exposed

### Laptop Setup (Do Once)

- [ ] Docker installed
- [ ] Monitoring folder created
- [ ] docker-compose-monitoring.yml file
- [ ] prometheus-remote.yml configured with server IP
- [ ] grafana-datasources.yml configured
- [ ] start-monitoring.sh script
- [ ] stop-monitoring.sh script
- [ ] Grafana dashboards downloaded and ready
- [ ] DBeaver connection profile saved
- [ ] Redis Desktop Manager profile saved

### Every Time You Monitor

**Starting:**
- [ ] Login to Admin UI
- [ ] Navigate to Monitoring Services
- [ ] Open ports (all or specific ones)
- [ ] Note the expiration time
- [ ] Start monitoring stack on laptop
- [ ] Wait 15-30 seconds
- [ ] Check Grafana dashboards loaded

**Ending:**
- [ ] Stop monitoring stack on laptop
- [ ] Close ports via Admin UI (or wait for auto-close)
- [ ] Verify ports closed in port status page

---

## 11. Future Enhancements (Nice to Have)

### Possible Improvements

**Cloud-Based Monitoring (Optional):**
- Send metrics to cloud service (Grafana Cloud, Datadog)
- No need to run monitoring stack locally
- Costs ~$50-100/month
- Good for teams or 24/7 monitoring

**Webhook Notifications:**
- Admin UI sends notification when port opened
- Integrate with Slack, Discord, email
- Track port access in team chat
- Get alerts when issues detected

**VPN Alternative:**
- Deploy VPN on server (Wireguard)
- Connect via VPN instead of opening ports
- More secure for always-on access
- Good for teams with multiple people monitoring

**Automated Port Closing:**
- Automatically close ports when laptop monitoring stops
- Integration with monitoring stack lifecycle
- Prevents forgetting ports open
- Scheduled closing (e.g., close at midnight)

**Enhanced Port Security:**
- IP address whitelist (only allow specific IPs)
- Rate limiting on monitoring ports
- Additional firewall rules
- Alert on excessive connection attempts

---

## 12. Glossary (What Do These Words Mean?)

**Port**: Like a door on your server. Can be open or closed. Each door has a number.

**Metrics**: Numbers that show how your system is performing (like a speedometer in a car).

**Prometheus**: Tool that collects metrics (numbers) from your server.

**Grafana**: Tool that shows metrics as pretty graphs and dashboards.

**DBeaver**: Tool for viewing and managing databases.

**Redis**: Fast memory storage (cache) for temporary data.

**PostgreSQL**: Database that stores permanent data.

**PgBouncer**: Manages database connections efficiently.

**Audit Trail**: Record of who did what and when (like a logbook).

**iptables**: Firewall rules on Linux that control what can come in/out.

**Container**: Isolated environment that runs an application (like a virtual box).

**Docker**: Tool that runs containers.

**SSH Tunnel**: Secure connection between two computers through encrypted channel.

**Rate Limiting**: Slowing down or blocking someone if they make too many requests.

**Validation**: Checking if something is correct or allowed.

---

## 13. Quick Reference

### Important URLs

**Server:**
- Main app: `https://your-domain.com`
- Admin UI: `https://your-domain.com/admin`
- Metrics: `https://your-domain.com/metrics`
- Health check: `https://your-domain.com/health`
- Port config: `https://your-domain.com/admin/monitoring/port-config`
- Port management: `https://your-domain.com/admin/monitoring/services`

**Laptop (when monitoring is running):**
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

### Common Commands

**Server:**
```bash
# Check logs
docker logs sms_receiver

# Check what's running
docker ps

# Check firewall rules
sudo iptables -L -n

# Check if port is in use
sudo lsof -i :9100
```

**Laptop:**
```bash
# Start monitoring
./start-monitoring.sh your-server-ip

# Stop monitoring
./stop-monitoring.sh

# Check monitoring status
./check-monitoring.sh

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets
```

### Port Numbers Quick Reference

| Service | Internal | External (Default) | Customizable? |
|---------|----------|-------------------|---------------|
| SMS Bridge | 8080 | 8080 | No (always exposed) |
| Metrics | 8080 | 9100 | Yes |
| PostgreSQL | 5432 | 5433 | Yes |
| PgBouncer | 6432 | 6434 | Yes |
| Redis | 6379 | 6380 | Yes |

---

## Document Information

**Version**: 2.3  
**Status**: Final Draft  
**Last Updated**: 2026-01-12  
**Next Review**: Q2 2026  
**Owner**: DevOps Team  

**Related Documents:**
- `SMS_Bridge_monitoring_snippets_v2.3.md` - Code examples and implementation
- `SMS_Bridge_tech_spec_v2.2.md` - Main technical specification
- `schema.sql` - Database schema
- `sms_settings.json` - Configuration file

**Changes from v2.2:**
- Removed Prometheus/Grafana from server
- Added on-demand port management
- Added configurable monitoring ports
- Minimal logging strategy
- Remote monitoring from laptop
- Improved security with auto-closing ports
- 60% reduction in server RAM usage
- 95% reduction in server disk usage

---

**Questions?** Contact the DevOps team or refer to `SMS_Bridge_monitoring_snippets_v2.3.md` for technical details.
