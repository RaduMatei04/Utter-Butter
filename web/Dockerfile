# Serverul web: nginx, varianta mică „alpine”
FROM nginx:1.27-alpine

# Înlocuim configurația implicită cu a noastră
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copiem fișierele SPA-ului în folderul servit de nginx
COPY public/ /usr/share/nginx/html/
