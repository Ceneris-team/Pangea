FROM node:20-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

# Vite congela las import.meta.env EN TIEMPO DE BUILD, así que la key de
# Google Maps tiene que entrar acá: sin este ARG, GOOGLE_MAPS_API_KEY
# queda vacía en el bundle y TODA pantalla con mapa (HU08, HU17, HU22)
# muestra "Falta configurar VITE_GOOGLE_MAPS_API_KEY".
#
# La key termina siendo visible en el JS servido: es inevitable en una SPA
# y por eso Google la protege por RESTRICCIÓN DE REFERRER, no por secreto.
# Antes de construir para un dominio nuevo hay que agregar ese dominio a
# las restricciones de la key en Google Cloud Console, o el mapa cargará
# en blanco con RefererNotAllowedMapError.
ARG VITE_GOOGLE_MAPS_API_KEY
ENV VITE_GOOGLE_MAPS_API_KEY=${VITE_GOOGLE_MAPS_API_KEY}

RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
