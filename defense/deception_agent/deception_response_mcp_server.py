# deception_response_mcp_server.py
"""
MCP Server for generating fake/deceptive responses to mislead attackers.

Provides tools to create realistic but fake:
- Environment files with credentials
- Admin panel HTML
- Configuration files
- Database backups
- API responses
"""

import json
import random
from typing import Dict, Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "DeceptionResponseServer",
    json_response=True,
)


# Fake data generators
def _random_hex(length: int) -> str:
    """Generate random hex string."""
    import secrets
    return secrets.token_hex(length // 2)


def _random_username() -> str:
    """Generate fake username."""
    usernames = ["admin", "root", "dbadmin", "apiuser", "developer", "deploy", "system", "service"]
    return random.choice(usernames) + str(random.randint(1, 99))


def _random_password() -> str:
    """Generate fake but realistic password."""
    parts = [
        random.choice(["Temp", "Test", "Demo", "Fake", "Honey", "Decoy"]),
        random.choice(["Pass", "Admin", "Key", "Secret", "Token"]),
        str(random.randint(100, 999)),
        random.choice(["!", "@", "#", "$"]),
    ]
    return "".join(parts)


def _random_api_key() -> str:
    """Generate fake API key."""
    prefixes = ["sk_live_", "pk_test_", "api_key_", "token_"]
    return random.choice(prefixes) + _random_hex(32)


def _random_db_name() -> str:
    """Generate fake database name."""
    names = ["production", "prod_db", "main", "app_data", "customers", "users_db", "inventory"]
    return random.choice(names) + "_" + str(random.randint(1, 99))


def _random_ip() -> str:
    """Generate fake internal IP."""
    return f"192.168.{random.randint(1, 254)}.{random.randint(1, 254)}"


@mcp.tool()
def generate_fake_env_file(endpoint: str = "/.env", include_aws: bool = True) -> Dict:
    """
    Generate a fake .env file with deceptive credentials.

    This creates realistic but fake environment variables including:
    - Database credentials pointing to honeypot DBs
    - API keys that trigger alerts when used
    - AWS/cloud credentials (fake)
    - JWT secrets and other tokens

    Args:
        endpoint: The endpoint that was probed (for context)
        include_aws: Whether to include fake AWS credentials

    Returns:
        Dictionary with fake .env content and metadata
    """
    fake_env_lines = [
        "# Environment Configuration",
        "# DO NOT COMMIT THIS FILE",
        "",
        "# Application",
        f"APP_NAME=ProductionAPI",
        f"APP_ENV=production",
        f"APP_DEBUG=false",
        f"APP_KEY={_random_hex(32)}",
        "",
        "# Database",
        f"DB_CONNECTION=mysql",
        f"DB_HOST={_random_ip()}",
        f"DB_PORT=3306",
        f"DB_DATABASE={_random_db_name()}",
        f"DB_USERNAME={_random_username()}",
        f"DB_PASSWORD={_random_password()}",
        "",
        "# Redis",
        f"REDIS_HOST={_random_ip()}",
        f"REDIS_PASSWORD={_random_password()}",
        f"REDIS_PORT=6379",
        "",
        "# API Keys",
        f"API_SECRET_KEY={_random_api_key()}",
        f"JWT_SECRET={_random_hex(64)}",
        f"SESSION_SECRET={_random_hex(32)}",
        "",
    ]

    if include_aws:
        fake_env_lines.extend([
            "# AWS Configuration",
            f"AWS_ACCESS_KEY_ID=AKIA{_random_hex(16).upper()}",
            f"AWS_SECRET_ACCESS_KEY={_random_hex(40)}",
            f"AWS_DEFAULT_REGION=us-east-1",
            f"AWS_BUCKET=prod-backups-{random.randint(1000, 9999)}",
            "",
        ])

    fake_env_lines.extend([
        "# Email",
        f"MAIL_USERNAME=noreply@{random.choice(['company', 'app', 'service'])}.com",
        f"MAIL_PASSWORD={_random_password()}",
        "",
        "# External Services",
        f"STRIPE_SECRET_KEY=sk_live_{_random_hex(24)}",
        f"TWILIO_AUTH_TOKEN={_random_hex(32)}",
        "",
    ])

    content = "\n".join(fake_env_lines)

    return {
        "content": content,
        "content_type": "text/plain",
        "filename": ".env",
        "size_bytes": len(content),
        "endpoint_probed": endpoint,
        "deception_type": "fake_credentials",
        "purpose": "Waste attacker time with fake DB/API credentials that lead to honeypots",
        "alert_triggers": [
            "DB connection attempts to fake IPs will alert",
            "API key usage attempts will trigger notifications",
            "AWS credential usage will be monitored",
        ],
    }


@mcp.tool()
def generate_fake_admin_panel(endpoint: str = "/admin") -> Dict:
    """
    Generate fake admin panel HTML with login form.

    Creates a realistic admin login page with:
    - Fake CSRF tokens
    - Session tracking
    - Convincing styling
    - Hidden tracking pixels

    Args:
        endpoint: The admin endpoint that was probed

    Returns:
        Dictionary with fake HTML content and metadata
    """
    session_id = _random_hex(32)
    csrf_token = _random_hex(64)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Panel - Login</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }}
        .login-container {{
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            width: 100%;
            max-width: 400px;
        }}
        h2 {{
            margin-top: 0;
            color: #333;
            text-align: center;
        }}
        .form-group {{
            margin-bottom: 20px;
        }}
        label {{
            display: block;
            margin-bottom: 5px;
            color: #666;
            font-weight: 500;
        }}
        input {{
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 14px;
            box-sizing: border-box;
        }}
        input:focus {{
            outline: none;
            border-color: #667eea;
        }}
        button {{
            width: 100%;
            padding: 12px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.3s;
        }}
        button:hover {{
            background: #5568d3;
        }}
        .footer {{
            margin-top: 20px;
            text-align: center;
            font-size: 12px;
            color: #999;
        }}
        .tracking {{
            position: absolute;
            width: 1px;
            height: 1px;
            opacity: 0;
        }}
    </style>
</head>
<body>
    <div class="login-container">
        <h2>🔐 Admin Panel</h2>
        <form action="/admin/login" method="POST" id="loginForm">
            <input type="hidden" name="_csrf" value="{csrf_token}">
            <input type="hidden" name="_session" value="{session_id}">

            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required autocomplete="username">
            </div>

            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required autocomplete="current-password">
            </div>

            <button type="submit">Login</button>

            <div class="footer">
                Admin Panel v2.3.1 &copy; 2024
            </div>
        </form>
    </div>

    <!-- Tracking pixel (honeypot marker) -->
    <img src="/track.gif?session={session_id}" class="tracking" alt="">

    <script>
        // Fake form validation
        document.getElementById('loginForm').addEventListener('submit', function(e) {{
            e.preventDefault();
            // In real scenario, this would POST to honeypot backend
            alert('Invalid credentials. Please try again.');
        }});
    </script>
</body>
</html>"""

    return {
        "content": html_content,
        "content_type": "text/html",
        "filename": "admin_login.html",
        "size_bytes": len(html_content),
        "endpoint_probed": endpoint,
        "deception_type": "fake_admin_panel",
        "purpose": "Capture login attempts and waste attacker time",
        "tracking_mechanisms": [
            f"Session ID {session_id} tracks this visitor",
            f"CSRF token {csrf_token[:16]}... tracks form submissions",
            "Tracking pixel logs page loads",
            "Form submissions captured for analysis",
        ],
    }


@mcp.tool()
def generate_fake_config(
    endpoint: str = "/config.json",
    config_format: str = "json",
) -> Dict:
    """
    Generate fake configuration file (JSON or YAML).

    Creates realistic configuration with:
    - Fake service endpoints
    - Fake authentication settings
    - Fake feature flags
    - Misleading architecture info

    Args:
        endpoint: The config endpoint that was probed
        config_format: Format of config file ("json" or "yaml")

    Returns:
        Dictionary with fake config content and metadata
    """
    fake_config = {
        "app": {
            "name": "ProductionAPI",
            "version": "2.3.1",
            "environment": "production",
            "debug": False,
            "maintenance_mode": False,
        },
        "database": {
            "primary": {
                "host": _random_ip(),
                "port": 3306,
                "database": _random_db_name(),
                "username": _random_username(),
                "password": _random_password(),
                "ssl": True,
            },
            "replica": {
                "host": _random_ip(),
                "port": 3306,
                "database": _random_db_name(),
                "username": f"{_random_username()}_readonly",
            },
        },
        "cache": {
            "driver": "redis",
            "host": _random_ip(),
            "port": 6379,
            "password": _random_password(),
            "prefix": "prod_cache:",
        },
        "services": {
            "api_gateway": f"https://api-{random.randint(1, 99)}.internal.company.local",
            "auth_service": f"https://auth.internal.company.local",
            "payment_processor": f"https://payments-{random.randint(1, 5)}.internal.company.local",
        },
        "security": {
            "jwt_secret": _random_hex(64),
            "encryption_key": _random_hex(32),
            "api_rate_limit": 1000,
            "allowed_origins": ["https://app.company.com"],
        },
        "features": {
            "advanced_analytics": True,
            "beta_features": False,
            "admin_panel_v2": True,
            "legacy_api": False,
        },
        "monitoring": {
            "sentry_dsn": f"https://{_random_hex(32)}@sentry.io/123456",
            "datadog_api_key": _random_api_key(),
        },
    }

    if config_format == "json":
        content = json.dumps(fake_config, indent=2)
        content_type = "application/json"
        filename = "config.json"
    else:
        # Simple YAML conversion
        import yaml
        content = yaml.dump(fake_config, default_flow_style=False)
        content_type = "text/yaml"
        filename = "config.yaml"

    return {
        "content": content,
        "content_type": content_type,
        "filename": filename,
        "size_bytes": len(content),
        "endpoint_probed": endpoint,
        "deception_type": "fake_config",
        "purpose": "Mislead attacker about infrastructure and expose honeypot services",
        "deception_elements": [
            "Fake internal IPs lead to honeypots",
            "Fake service URLs are monitored",
            "Credentials trigger alerts when used",
            "Feature flags suggest non-existent capabilities",
        ],
    }


@mcp.tool()
def generate_fake_backup(endpoint: str = "/backup.sql", backup_type: str = "sql") -> Dict:
    """
    Generate fake database backup or archive file content.

    Creates realistic backup file content with:
    - Fake SQL dump with fake user data
    - Fake table structures
    - Misleading database schema
    - Fake sensitive data

    Args:
        endpoint: The backup endpoint that was probed
        backup_type: Type of backup ("sql" or "tar")

    Returns:
        Dictionary with fake backup content and metadata
    """
    if backup_type == "sql":
        fake_users = []
        for i in range(5):
            fake_users.append({
                "id": i + 1,
                "username": _random_username(),
                "email": f"{_random_username()}@company.local",
                "password_hash": f"$2b$10${_random_hex(44)}",
                "role": random.choice(["user", "admin", "moderator"]),
                "api_key": _random_api_key(),
            })

        sql_content = f"""-- MySQL dump 10.13  Distrib 8.0.32
-- Host: {_random_ip()}    Database: {_random_db_name()}
-- ------------------------------------------------------
-- Server version\t8.0.32

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL,
  `email` varchar(100) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role` varchar(20) DEFAULT 'user',
  `api_key` varchar(100) DEFAULT NULL,
  `created_at` timestamp DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES
"""

        # Add fake user data
        user_inserts = []
        for i, user in enumerate(fake_users, 1):
            user_inserts.append(
                f"({user['id']},'{user['username']}','{user['email']}','{user['password_hash']}','{user['role']}','{user['api_key']}','2024-01-{random.randint(10, 28)} 10:23:45')"
            )

        sql_content += ",\n".join(user_inserts)
        sql_content += ";\n/*!40000 ALTER TABLE `users` ENABLE KEYS */;\nUNLOCK TABLES;\n"

        # Add more fake tables
        sql_content += f"""
--
-- Table structure for table `sessions`
--

DROP TABLE IF EXISTS `sessions`;
CREATE TABLE `sessions` (
  `id` varchar(100) NOT NULL,
  `user_id` int DEFAULT NULL,
  `token` varchar(255) NOT NULL,
  `expires_at` timestamp NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

--
-- Table structure for table `api_keys`
--

DROP TABLE IF EXISTS `api_keys`;
CREATE TABLE `api_keys` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `key_hash` varchar(255) NOT NULL,
  `name` varchar(100) DEFAULT NULL,
  `permissions` json DEFAULT NULL,
  `created_at` timestamp DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Dump completed on 2024-11-22 14:35:22
"""

        content = sql_content
        content_type = "application/sql"
        filename = "database_backup.sql"

    else:  # tar listing
        content = f"""drwxr-xr-x root/root         0 2024-11-22 14:30 ./
drwxr-xr-x root/root         0 2024-11-22 14:30 ./config/
-rw-r--r-- root/root      2048 2024-11-22 14:30 ./config/database.yml
-rw-r--r-- root/root      1024 2024-11-22 14:30 ./config/secrets.yml
drwxr-xr-x root/root         0 2024-11-22 14:30 ./data/
-rw-r--r-- root/root   1048576 2024-11-22 14:30 ./data/{_random_db_name()}.sql
-rw-r--r-- root/root    524288 2024-11-22 14:30 ./data/user_exports.csv
drwxr-xr-x root/root         0 2024-11-22 14:30 ./keys/
-rw------- root/root      1679 2024-11-22 14:30 ./keys/id_rsa
-rw-r--r-- root/root       400 2024-11-22 14:30 ./keys/id_rsa.pub
-rw-r--r-- root/root       512 2024-11-22 14:30 ./keys/api_keys.txt
"""
        content_type = "text/plain"
        filename = "backup.tar.gz.listing"

    return {
        "content": content,
        "content_type": content_type,
        "filename": filename,
        "size_bytes": len(content),
        "endpoint_probed": endpoint,
        "deception_type": "fake_backup",
        "purpose": "Provide fake database dump to waste attacker time analyzing fake data",
        "deception_elements": [
            "All user credentials are fake",
            "API keys trigger alerts if used",
            "Email addresses point to honeypot domains",
            "Database structure suggests non-existent schema",
        ],
    }


@mcp.tool()
def generate_fake_api_response(
    endpoint: str = "/api/users",
    response_type: str = "user_list",
) -> Dict:
    """
    Generate fake API JSON response.

    Creates realistic API responses with:
    - Fake user data
    - Fake authentication tokens
    - Fake business data
    - Tracking tokens

    Args:
        endpoint: The API endpoint that was probed
        response_type: Type of response ("user_list", "auth", "config", "stats")

    Returns:
        Dictionary with fake API response and metadata
    """
    if response_type == "user_list":
        fake_data = {
            "status": "success",
            "data": {
                "users": [
                    {
                        "id": i,
                        "username": _random_username(),
                        "email": f"{_random_username()}@company.local",
                        "role": random.choice(["user", "admin", "moderator"]),
                        "api_key": _random_api_key(),
                        "last_login": f"2024-11-{random.randint(15, 22)}T{random.randint(10, 20)}:00:00Z",
                    }
                    for i in range(1, 6)
                ],
                "total": 5,
                "page": 1,
                "per_page": 10,
            },
            "metadata": {
                "request_id": _random_hex(16),
                "timestamp": "2024-11-22T14:30:00Z",
                "api_version": "2.1",
            },
        }
    elif response_type == "auth":
        fake_data = {
            "status": "success",
            "data": {
                "token": f"Bearer {_random_hex(64)}",
                "refresh_token": _random_hex(64),
                "expires_in": 3600,
                "user": {
                    "id": random.randint(1, 100),
                    "username": _random_username(),
                    "role": "admin",
                    "permissions": ["read", "write", "admin"],
                },
            },
        }
    elif response_type == "stats":
        fake_data = {
            "status": "success",
            "data": {
                "total_users": random.randint(1000, 5000),
                "active_sessions": random.randint(50, 200),
                "api_calls_today": random.randint(10000, 50000),
                "database_size_mb": random.randint(500, 2000),
                "uptime_hours": random.randint(1000, 5000),
            },
            "internal": {
                "server_id": _random_hex(8),
                "datacenter": random.choice(["us-east-1", "us-west-2", "eu-west-1"]),
            },
        }
    else:  # config
        fake_data = {
            "status": "success",
            "data": {
                "features": {
                    "authentication": "enabled",
                    "rate_limiting": "enabled",
                    "admin_panel": "enabled",
                    "debug_mode": "disabled",
                },
                "endpoints": {
                    "api_base": "https://api.company.local",
                    "auth": "https://auth.company.local",
                    "cdn": "https://cdn.company.local",
                },
                "version": "2.3.1",
            },
        }

    content = json.dumps(fake_data, indent=2)

    return {
        "content": content,
        "content_type": "application/json",
        "filename": f"{response_type}_response.json",
        "size_bytes": len(content),
        "endpoint_probed": endpoint,
        "deception_type": "fake_api_response",
        "purpose": "Provide fake API data to mislead attacker about system capabilities",
        "deception_elements": [
            "All tokens and keys trigger alerts if used",
            "User data is completely fabricated",
            "Internal server IDs are monitored",
            "Endpoints point to honeypot services",
        ],
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
