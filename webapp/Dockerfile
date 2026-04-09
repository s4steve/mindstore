FROM nginx:alpine
WORKDIR /usr/share/nginx/html

COPY index.html .
COPY nav.js .
COPY tasks.html .
COPY contacts.html .
COPY home.html .
COPY wiki.html .

# Remove default nginx config; ours is injected at startup via envsubst
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# openssl is needed by the htpasswd generation script
RUN apk add --no-cache openssl

# Generate htpasswd from WEB_USERNAME / WEB_PASSWORD at container startup
COPY 10-generate-htpasswd.sh /docker-entrypoint.d/10-generate-htpasswd.sh
RUN chmod +x /docker-entrypoint.d/10-generate-htpasswd.sh

# nginx docker image processes /etc/nginx/templates/*.template via envsubst on start
EXPOSE 3000
