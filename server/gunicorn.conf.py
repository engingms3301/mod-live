import os
bind = '0.0.0.0:' + os.environ.get('PORT', '8080')
workers = 1
worker_class = 'gthread'
threads = 4
timeout = 30
graceful_timeout = 20
keepalive = 5
limit_request_line = 4094
limit_request_fields = 30
limit_request_field_size = 8190
accesslog = None
errorlog = '-'
# Network HTTPS termination belongs to the hosting platform.
forwarded_allow_ips = ''
