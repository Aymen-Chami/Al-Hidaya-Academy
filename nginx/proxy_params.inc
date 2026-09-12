proxy_http_version 1.1;
proxy_set_header Connection "";
# $http_host keeps the port, so the API's same-origin (Origin vs Host) check works on :8080 too.
proxy_set_header Host $http_host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $fwd_proto;
proxy_read_timeout 30s;
