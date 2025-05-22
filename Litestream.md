# Litestream Configuration Guide for LinuxReport

This guide explains how to set up Litestream for continuous replication of your SQLite database across your LinuxReport servers.

## What is Litestream?

Litestream is a powerful tool that provides continuous replication for SQLite databases. It works by streaming SQLite WAL (Write-Ahead Logging) changes to a replica in real-time, ensuring your data is always backed up and available. For LinuxReport, this means:

- Real-time replication of your SQLite cache database
- Automatic failover capabilities
- Minimal performance impact
- Simple configuration and maintenance

## Prerequisites

- Two Arch Linux servers (primary and replica)
- SSH access between servers
- Root or sudo access on both servers
- Your existing SQLite database

## Installation

1. Install Litestream on both servers:

```bash
# Install Litestream using pacman
sudo pacman -S litestream
```

2. Verify the installation:

```bash
litestream version
```

## SSH Key Setup

1. Generate SSH keys on the primary server if you haven't already:

```bash
ssh-keygen -t ed25519 -C "litestream-replication"
```

2. Copy the public key to the replica server:

```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub user@replica-server
```

3. Test the connection:

```bash
ssh user@replica-server
```

## Configuration

### 1. Create Litestream Configuration

Create the configuration file on the primary server:

```bash
sudo mkdir -p /etc/litestream
sudo nano /etc/litestream/litestream.yml
```

Add the following configuration:

```yaml
# /etc/litestream/litestream.yml
dbs:
  - path: /path/to/your/cache.db
    replicas:
      - url: sftp://user@replica-server/path/to/replica/cache.db
        retention: 24h
        sync-interval: 5m  # Since data changes infrequently
        validation-interval: 1h
```

### 2. Configure Systemd Service

Create a systemd service file:

```bash
sudo nano /etc/systemd/system/litestream.service
```

Add the following content:

```ini
[Unit]
Description=Litestream replication service
After=network.target

[Service]
Type=simple
User=your-user
ExecStart=/usr/bin/litestream replicate -config /etc/litestream/litestream.yml
Restart=always
RestartSec=1
# Add resource limits for infrequent changes
CPUQuota=20%
MemoryLimit=256M

[Install]
WantedBy=multi-user.target
```

### 3. Start and Enable the Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable litestream
sudo systemctl start litestream
```

## Monitoring and Management

### Check Replication Status

```bash
litestream databases
```

### View Replication Logs

```bash
journalctl -u litestream -f
```

### Manual Replication

```bash
litestream replicate -config /etc/litestream/litestream.yml
```

## Best Practices

1. **Regular Backups**
   - Keep daily backups of your replica
   - Test restoration procedures regularly

2. **Monitoring**
   - Set up monitoring for the Litestream service
   - Monitor disk space on both servers
   - Check replication lag

3. **Security**
   - Use dedicated SSH keys for replication
   - Restrict SSH access to replication IPs
   - Regular key rotation

4. **Performance**
   - Adjust sync-interval based on your needs
   - Monitor system resources
   - Consider using tmpfs for WAL files

## Troubleshooting

### Common Issues

1. **Replication Not Starting**
   - Check SSH connectivity
   - Verify file permissions
   - Check systemd logs

2. **High Replication Lag**
   - Check network connectivity
   - Monitor system resources
   - Adjust sync-interval

3. **Disk Space Issues**
   - Monitor disk usage
   - Adjust retention period
   - Clean up old replicas

### Useful Commands

```bash
# Check replication status
litestream databases

# View detailed logs
journalctl -u litestream -f

# Manual replication
litestream replicate -config /etc/litestream/litestream.yml
```

## Advanced Features

### 1. Multiple Replicas

You can configure multiple replicas for redundancy:

```yaml
dbs:
  - path: /path/to/your/cache.db
    replicas:
      - url: sftp://user@replica1/path/to/replica/cache.db
      - url: sftp://user@replica2/path/to/replica/cache.db
```

### 2. Retention Policies

Configure how long to keep old replicas:

```yaml
replicas:
  - url: sftp://user@replica-server/path/to/replica/cache.db
    retention: 24h  # Keep replicas for 24 hours
```

### 3. Validation

Enable periodic validation of replicas:

```yaml
replicas:
  - url: sftp://user@replica-server/path/to/replica/cache.db
    validation-interval: 1h  # Validate every hour
```

## Understanding Retention

### Retention in Continuous Replication

The retention policy in Litestream works differently from traditional backup systems:

1. **Point-in-Time Recovery**
   - Litestream maintains a continuous stream of WAL (Write-Ahead Logging) files
   - Each WAL file represents a point-in-time snapshot of your database
   - The retention period (e.g., `retention: 24h`) determines how long these WAL files are kept
   - This allows you to restore your database to any point within the retention window

2. **How Retention Works**
   ```yaml
   replicas:
     - url: sftp://user@replica-server/path/to/replica/cache.db
       retention: 24h  # Keep WAL files for 24 hours
   ```
   - Litestream continuously streams WAL files to the replica
   - Old WAL files are automatically deleted after the retention period
   - The main database file is always kept
   - You can restore to any point within the last 24 hours

3. **Storage Considerations**
   - WAL files are typically small (few MB each)
   - Storage usage depends on:
     - How frequently your database changes
     - The retention period
     - The number of replicas
   - Example: If your database changes 100MB per day and you keep 24 hours of WAL files, you might use ~100MB of additional storage

## Maintenance

### Regular Tasks

1. **Weekly**
   - Check replication status
   - Monitor disk usage
   - Review logs

2. **Monthly**
   - Test failover procedures
   - Verify backup integrity
   - Update Litestream

3. **Quarterly**
   - Review and update retention policies
   - Check security settings
   - Performance optimization

## Conclusion

This setup provides a robust replication solution for your LinuxReport system, ensuring your SQLite cache database is continuously backed up and available. The configuration is optimized for your use case where:
- Data changes infrequently (hourly or less)
- Total data size is small
- High availability isn't critical
- Resource usage should be minimized

Remember to:
- Regularly test your backup and restore procedures
- Monitor system resources and replication status
- Keep your Litestream installation up to date
- Document any custom configurations or changes

For more information, visit the [official Litestream documentation](https://litestream.io/docs/). 