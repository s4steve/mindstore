FROM nginx:alpine
WORKDIR /usr/share/nginx/html

COPY index.html .
COPY nav.js .
COPY tasks.html .
COPY contacts.html .
COPY home.html .

# Remove default nginx config; ours is generated at startup
RUN rm /etc/nginx/conf.d/default.conf

# Copy nginx config templates (picked at startup based on cert presence)
RUN mkdir -p /etc/nginx/conf-templates
COPY nginx-https.conf.tmpl /etc/nginx/conf-templates/
COPY nginx-http.conf.tmpl  /etc/nginx/conf-templates/

# openssl is needed by the htpasswd generation script
RUN apk add --no-cache openssl

# Generate htpasswd from WEB_USERNAME / WEB_PASSWORD at container startup
COPY 10-generate-htpasswd.sh /docker-entrypoint.d/10-generate-htpasswd.sh
RUN chmod +x /docker-entrypoint.d/10-generate-htpasswd.sh

# Generate nginx config (HTTPS or HTTP) based on cert availability
COPY 25-generate-nginx-config.sh /docker-entrypoint.d/25-generate-nginx-config.sh
RUN chmod +x /docker-entrypoint.d/25-generate-nginx-config.sh

EXPOSE 3000
