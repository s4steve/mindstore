FROM nginx:alpine
WORKDIR /usr/share/nginx/html

COPY index.html .

# Remove default nginx config; ours is injected at startup via envsubst
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# nginx docker image processes /etc/nginx/templates/*.template via envsubst on start
EXPOSE 3000
