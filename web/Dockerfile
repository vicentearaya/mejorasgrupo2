FROM node:18-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .

# Accept build arguments
ARG VITE_API_RRHH
ARG VITE_API_URL
ARG VITE_API_INVENTARIO
ARG VITE_API_LOGISTICA
ARG VITE_GOOGLE_MAPS_API_KEY

# Set as environment variables for the build
ENV VITE_API_RRHH=$VITE_API_RRHH
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_API_INVENTARIO=$VITE_API_INVENTARIO
ENV VITE_API_LOGISTICA=$VITE_API_LOGISTICA
ENV VITE_GOOGLE_MAPS_API_KEY=$VITE_GOOGLE_MAPS_API_KEY

RUN npm run build

FROM nginx:stable-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
