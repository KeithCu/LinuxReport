# Litestream Configuration Guide for LinuxReport

This guide explains how to set up Litestream for continuous replication of your SQLite database across your LinuxReport servers.

## What is Litestream?

Litestream is a powerful tool that provides continuous replication for SQLite databases. It works by streaming SQLite WAL (Write-Ahead Logging) changes to a replica in real-time, ensuring your data is always backed up and available. For LinuxReport, this means:

- Real-time replication of your SQLite cache database
- Automatic failover capabilities
- Minimal performance impact
- Simple configuration and maintenance

## Alternative Approaches to Database Replication

For applications that primarily deal with feed data and updates, there are simpler alternatives to Litestream that may be more appropriate:

### Object Store with Metadata-Based Updates

This approach is particularly well-suited for feed-based applications where:
- Data changes are infrequent and predictable
- You want to minimize complexity
- You want to avoid running separate processes

#### Implementation Strategy:

1. **Direct Object Store Access with Metadata**
   - Servers are configured to fetch directly from object store instead of original URLs
   - Cache is configured with a 15-minute TTL
   - Each feed entry includes metadata about its last update time
   - When cache expires:
     - Check metadata to determine if new data is available
     - Only fetch if metadata indicates changes
   - Benefits:
     - No separate process needed
     - Efficient bandwidth usage (only fetch when needed)
     - Simple architecture
     - Natural load distribution
     - Built-in redundancy through object store
   - Implementation considerations:
     - Ensure object store has proper caching headers
     - Implement metadata comparison logic
     - Handle object store authentication securely

2. **Controlled File Swap**
   - Main application pauses briefly every 5 minutes
   - Swaps in new replicated database file
   - Resumes operations
   - Considerations:
     - Need to handle concurrent requests during pause
     - May need to recreate diskcache instance
     - Brief service interruption
     - Simpler than complex replication logic

3. **Direct S3 Access**
   - Read directly from S3
   - Benefits:
     - No file swapping needed
     - No need to pause application
     - Simpler implementation
   - Drawbacks:
     - Higher latency than local disk
     - S3 costs for storage and requests
     - Need to handle S3 credentials

#### When to Choose This Over Litestream:
- Your application primarily deals with feed data
- Updates are infrequent and predictable
- You're already using object storage for feeds
- You want to minimize infrastructure complexity
- You don't need point-in-time recovery
- Your data changes are small and incremental

#### When to Stick with Litestream:
- You need continuous replication
- Point-in-time recovery is important
- Your database changes are frequent and unpredictable
- You need atomic transactions across replicas
- Your application makes many small changes to the database

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

5. **Handling Replicated Database Access**
   - **Option 1: Direct Object Store Access with Metadata**
     - Servers are configured to fetch directly from object store instead of original URLs
     - Cache is configured with a 15-minute TTL
     - Each feed entry includes metadata about its last update time
     - When cache expires:
       - Check metadata to determine if new data is available
       - Only fetch if metadata indicates changes
     - Benefits:
       - No separate process needed
       - Efficient bandwidth usage (only fetch when needed)
       - Simple architecture
       - Natural load distribution
       - Built-in redundancy through object store
     - Implementation considerations:
       - Ensure object store has proper caching headers
       - Implement metadata comparison logic
       - Handle object store authentication securely
       - Consider using CDN for better performance

   - **Option 2: Controlled File Swap**
     - Main application pauses briefly every 5 minutes
     - Swaps in new replicated database file
     - Resumes operations
     - Considerations:
       - Need to handle concurrent requests during pause
       - May need to recreate diskcache instance
       - Brief service interruption
       - Simpler than complex replication logic

   - **Option 3: Direct S3 Access**
     - Read directly from S3
     - Benefits:
       - No file swapping needed
       - No need to pause application
       - Simpler implementation
     - Drawbacks:
       - Higher latency than local disk
       - S3 costs for storage and requests
       - Need to handle S3 credentials

   - **Recommendation:**
     - Start with Option 1 (Direct Object Store Access with Metadata)
     - Provides best balance of performance and simplicity
     - No need to pause application
     - Efficient use of bandwidth
     - Clean separation of concerns

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