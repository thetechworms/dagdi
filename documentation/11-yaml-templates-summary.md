# YAML Configuration Templates Summary

## Available Templates

Dagdi provides two complete template files to help you get started with your configuration.

### 1. Old Format Template (Nested Services)

**File:** `config/dagdi-template-old-format.yaml`

**Use this if:**
- You have 1-2 environments
- Each environment has unique services
- You prefer simplicity
- You're just getting started

**Key Features:**
- Services defined inline with servers
- Simple structure
- Good for learning
- No global service management needed

**Example Structure:**
```yaml
products:
  - name: myapp
    environments:
      - name: dev
        servers:
          ssh:
            username: ubuntu
            key_path: ~/.ssh/id_rsa
          items:
            - name: server1
              services:
                - name: nginx
                  type: docker
                - name: postgresql
                  type: docker
```

**Pros:**
- ✓ Simple and straightforward
- ✓ Everything in one place
- ✓ Easy to understand

**Cons:**
- ✗ Services repeated across environments
- ✗ Harder to maintain at scale
- ✗ Larger files

### 2. New Format Template (Global Services)

**File:** `config/dagdi-template-new-format.yaml`

**Use this if:**
- You have 3+ environments
- Services are repeated across environments
- You want to follow DRY principles
- You need centralized management

**Key Features:**
- Services defined globally once
- Servers reference services by name
- Cleaner structure
- Easier to maintain

**Example Structure:**
```yaml
services:
  - name: nginx
    type: docker
  - name: postgresql
    type: docker

products:
  - name: myapp
    environments:
      - name: dev
        servers:
          ssh:
            username: ubuntu
            key_path: ~/.ssh/id_rsa
          items:
            - name: server1
              service_names: [nginx, postgresql]
      - name: prod
        servers:
          ssh:
            username: ubuntu
            key_path: ~/.ssh/id_rsa
          items:
            - name: server1
              service_names: [nginx, postgresql]
```

**Pros:**
- ✓ Single service definition
- ✓ Easy to maintain
- ✓ Smaller files
- ✓ Scales well

**Cons:**
- ✗ Requires managing global services
- ✗ Slightly more complex

## Quick Start Guide

### Using Old Format Template

```bash
# 1. Copy the template to the default config directory
mkdir -p ~/.config/dagdi
cp config/dagdi-template-old-format.yaml ~/.config/dagdi/dagdi-myapp.yaml

# 2. Edit the file with your infrastructure details
nano ~/.config/dagdi/dagdi-myapp.yaml

# 3. Validate the configuration
dagdi config validate

# 4. Start using Dagdi
dagdi discovery products
```

### Using New Format Template

```bash
# 1. Copy the template to the default config directory
mkdir -p ~/.config/dagdi
cp config/dagdi-template-new-format.yaml ~/.config/dagdi/dagdi-myapp.yaml

# 2. Edit the file with your infrastructure details
nano ~/.config/dagdi/dagdi-myapp.yaml

# 3. Validate the configuration
dagdi config validate

# 4. Start using Dagdi
dagdi discovery products
```

## Template Comparison

| Feature | Old Format | New Format |
|---------|-----------|-----------|
| **File** | `dagdi-template-old-format.yaml` | `dagdi-template-new-format.yaml` |
| **Services** | Nested in servers | Global section |
| **References** | Direct definitions | By name |
| **Duplication** | High | None |
| **Complexity** | Low | Medium |
| **Scalability** | Poor | Excellent |
| **Best for** | Small projects | Large projects |

## What's in Each Template

### Old Format Template Includes:

- ✓ Product definition
- ✓ Multiple environments (dev, prod)
- ✓ Multiple servers per environment
- ✓ Services nested in servers
- ✓ SSH configuration examples
- ✓ Global settings
- ✓ Detailed comments explaining each section

### New Format Template Includes:

- ✓ Global services section
- ✓ 6 example services (nginx, postgresql, redis, syslog, prometheus, grafana)
- ✓ Product definition
- ✓ Multiple environments (dev, prod, staging)
- ✓ Multiple servers per environment
- ✓ Service references by name
- ✓ SSH configuration examples
- ✓ Global settings
- ✓ Detailed comments explaining each section
- ✓ Benefits documentation in comments

## Migration Between Formats

### From Old to New Format

If you start with the old format and want to migrate:

1. **Identify unique services** across all environments
2. **Create global services section** at the top
3. **Replace nested services** with service_names references
4. **Validate** with `dagdi config validate`
5. **Test** all commands

See `documentation/10-yaml-configuration-migration.md` for detailed steps.

### From New to Old Format

If you start with the new format and want to go back:

1. **Copy service definitions** from global section
2. **Paste into each server** that needs them
3. **Remove global services section**
4. **Remove service_names** from servers
5. **Validate** with `dagdi config validate`

## Configuration Validation

After creating your configuration, always validate it:

```bash
dagdi config validate
```

Expected output:
```
✓ Configuration is valid!
  Products: 1
  Environments: 2
  Servers: 3
  Services: 5
```

## Common Customizations

### Adding a New Service (Old Format)

```yaml
services:
  - name: redis
    type: docker
    friendly_name: Redis Cache
    port: 6379
    config:
      container_name: redis
```

### Adding a New Service (New Format)

```yaml
services:
  - name: redis
    type: docker
    friendly_name: Redis Cache
    port: 6379
    config:
      container_name: redis

# Then reference it in servers:
servers:
  - name: server1
    service_names: [nginx, redis]
```

### Adding a New Environment (Old Format)

```yaml
- name: staging
  servers:
    - name: server1
      type: ubuntu
      ips: [10.0.3.10]
      ssh:
        username: ubuntu
        key_path: ~/.ssh/id_rsa
      services:
        - name: nginx
          type: docker
          config:
            container_name: nginx
```

### Adding a New Environment (New Format)

```yaml
- name: staging
  servers:
    - name: server1
      type: ubuntu
      ips: [10.0.3.10]
      ssh:
        username: ubuntu
        key_path: ~/.ssh/id_rsa
      service_names: [nginx, postgresql]
      # Services already defined globally!
```

## Tips and Best Practices

### For Old Format:

1. Keep services organized by type (docker, systemd)
2. Use consistent naming conventions
3. Document service configurations in comments
4. Consider migrating when you add more environments

### For New Format:

1. Define all services at the top of the file
2. Use descriptive service names
3. Include friendly_name for display purposes
4. Group related services together
5. Add comments explaining service purposes

## Support

For more information:

- See `documentation/10-yaml-configuration-migration.md` for migration guide
- See `documentation/03-configuration-reference.md` for detailed configuration options
- See `documentation/02-architecture-and-flow.md` for architecture overview

## Next Steps

1. Choose a template (old or new format)
2. Copy it to `~/.config/dagdi/dagdi-myapp.yaml`
3. Customize with your infrastructure
4. Run `dagdi config validate`
5. Start using Dagdi commands!
