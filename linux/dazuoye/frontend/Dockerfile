# 使用 Nginx Alpine 镜像提供前端静态文件服务
FROM nginx:alpine

# 复制 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 复制静态文件
COPY static /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]