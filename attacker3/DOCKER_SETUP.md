# Docker Setup for RedTeamAgent

## Fixing Docker Authentication Issues

If you see errors like "email must be verified before using account", you need to authenticate with Docker Hub.

### Step 1: Log in to Docker Hub

```bash
docker login
```

You'll be prompted for:
- **Username**: Your Docker Hub username
- **Password**: Your Docker Hub password (or Personal Access Token)

**Note:** If you don't have a Docker Hub account, create one at https://hub.docker.com and verify your email address.

### Step 2: Verify Your Email

Make sure your Docker Hub account email is verified. Check your email inbox for a verification email from Docker.

### Step 3: Build the Image

Once authenticated, build from the `attacker3` directory:

```bash
cd attacker3
docker build -t redteamagent .
```

### Alternative: Use Personal Access Token

If you prefer using a Personal Access Token instead of your password:

1. Go to https://hub.docker.com/settings/security
2. Create a new Personal Access Token
3. Use it as your password when running `docker login`

## Complete Build and Run Commands

```bash
# 1. Navigate to attacker3 directory
cd attacker3

# 2. Make sure your API key is set in src/redteamagent/config/config.json

# 3. Build the image
docker build -t redteamagent .

# 4. Run with host network (to access localhost:3000)
docker run -it --rm --network host redteamagent

# 5. Inside the container, run:
ReAct
# or
RedTeamAgent

# 6. When prompted, enter your attack task:
# Attack the web application running on http://localhost:3000. Find vulnerabilities and extract sensitive information from the Pet Grooming by Sofia application.
```

## Troubleshooting

### "email must be verified" error
- Verify your email address in Docker Hub account settings
- Make sure you're logged in: `docker login`

### "unauthorized" error
- Your Docker Hub session may have expired
- Run `docker login` again

### Can't access localhost:3000 from container
- Use `--network host` flag when running
- Or use `host.docker.internal:3000` instead of `localhost:3000`

