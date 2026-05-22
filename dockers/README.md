# Sistema Docker (replica)

Replica del esquema de `/home/stvdev/Proyectos/personal/GYM/dockers`:

- `database/compose.yml` (PostgreSQL)
- `redis/compose.yml` (Redis)
- `evolution/compose.yml` (Evolution API)

Todos los servicios usan una red externa compartida: `hackiathon_network`.

## 1) Crear la red (una sola vez)

```bash
docker network create hackiathon_network
```

## 2) Preparar variables de entorno

```bash
cp database/.env.example database/.env
cp evolution/.env.example evolution/.env
```

Edita los archivos `.env` segun tu entorno.

## 3) Levantar servicios

Puedes levantar todos los servicios a la vez con un solo comando:

```bash
docker compose -f database/compose.yml -f redis/compose.yml -f evolution/compose.yml up -d
```

O individualmente si lo prefieres:

```bash
docker compose -f database/compose.yml up -d
docker compose -f redis/compose.yml up -d
docker compose -f evolution/compose.yml up -d
```

## 4) Verificar

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
```

## 5) Bajar servicios

Puedes apagar todos los servicios con un solo comando:

```bash
docker compose -f database/compose.yml -f redis/compose.yml -f evolution/compose.yml down
```

O individualmente:

```bash
docker compose -f database/compose.yml down
docker compose -f redis/compose.yml down
docker compose -f evolution/compose.yml down
```
