# Admin Dashboard Configuration

LinuxReport supports two complementary admin dashboards:

## 1. Flask-MonitoringDashboard (Optional)

Flask-MonitoringDashboard provides automatic endpoint performance monitoring, request tracking, and error analysis. It's already installed and configured but disabled by default.

### Features
- Automatic endpoint performance monitoring
- Request/response time tracking
- Error tracking and analysis
- Outlier detection
- User monitoring

### Enable Flask-MonitoringDashboard

To enable Flask-MonitoringDashboard:

1. **Set FLASK_DASHBOARD to True** in `shared.py`:
   ```python
   FLASK_DASHBOARD = True
   ```

2. **Configure credentials** in `config.yaml`:
   ```yaml
   admin:
     dashboard:
       username: "your_username"
       password: "your_password"
   ```

3. **Restart the application**

4. **Access the dashboard** at `/dashboard`

### What Flask-MonitoringDashboard Provides

- **Endpoint Performance**: Automatic monitoring of all Flask routes
- **Request Metrics**: Response times, throughput, error rates per endpoint
- **Outlier Detection**: Identifies slow or problematic requests
- **User Monitoring**: Tracks user activity patterns
- **Database Monitoring**: If using SQLAlchemy

## 2. Custom Admin Dashboard (`/admin/dashboard`)

Our custom dashboard provides application-specific metrics that Flask-MonitoringDashboard doesn't track:

### Features
- **Feed Health Monitoring**: Last fetch times, feed status (healthy/stale/error)
- **LLM Model Performance**: Success rates, usage statistics per model
- **Application Performance**: Custom render times, request counts
- **Rate Limit Statistics**: IP and endpoint tracking

### Access

Navigate to `/admin/dashboard` when logged in as admin.

## Comparison

| Feature | Flask-MonitoringDashboard | Custom Dashboard |
|---------|---------------------------|------------------|
| Endpoint monitoring | ✅ Automatic | ❌ Not included |
| Feed health | ❌ Not included | ✅ Tracked |
| LLM model stats | ❌ Not included | ✅ Tracked |
| Request performance | ✅ Detailed | ✅ Basic |
| Error tracking | ✅ Automatic | ❌ Not included |
| Custom metrics | Limited | ✅ Full support |

## Recommendation

**Use both dashboards together:**
- Enable Flask-MonitoringDashboard for automatic endpoint monitoring
- Use the custom dashboard (`/admin/dashboard`) for application-specific metrics

This gives you comprehensive monitoring coverage:
- Flask-MonitoringDashboard handles endpoint-level performance
- Custom dashboard handles application-level metrics (feeds, LLM models)

## Performance Impact

- **Flask-MonitoringDashboard**: Minimal overhead for endpoint monitoring
- **Custom Dashboard**: No performance impact (reads from cache only)

Both dashboards are designed to be lightweight and not impact production performance.

