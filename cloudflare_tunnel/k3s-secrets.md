K3s notes: Uploading credentials and running cloudflared in K3s

1. Create a Kubernetes secret with the credentials file

kubectl -n sms-bridge create secret generic cloudflared-credentials --from-file=credentials-file.json=./credentials-file.json

2. Run cloudflared as a deployment using the official image and mount the secret as a volume

Example minimal manifest snippet:

apiVersion: v1
kind: Deployment
metadata:
  name: cloudflared
  namespace: sms-bridge
spec:
  replicas: 1
  selector:
    matchLabels:
      app: cloudflared
  template:
    metadata:
      labels:
        app: cloudflared
    spec:
      containers:
      - name: cloudflared
        image: cloudflare/cloudflared:2024.4.0
        args:
        - tunnel
        - run
        - --config
        - /etc/cloudflared/config.yml
        volumeMounts:
        - name: cloudflared-creds
          mountPath: /etc/cloudflared/credentials-file.json
          subPath: credentials-file.json
      volumes:
      - name: cloudflared-creds
        secret:
          secretName: cloudflared-credentials

3. Create a configmap with your `config.yml` and mount it or bake it into the image.
4. Ensure DNS records in Cloudflare point to the tunnel.

Security notes:
- Keep `credentials-file.json` in a sealed secret store or restricted bucket until creating the K8s secret.
- Use RBAC to limit access to the `sms-bridge` namespace where the secret is stored.
