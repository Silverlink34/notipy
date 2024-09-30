# Notipy.py
Downloads and stores various API data to a Redis server!

This guide will help you get a new Redis Timeseries server up and running, or if you already have one, you can skip to the .env file configuration section and get started immediately!

## Requirements
- a running Docker instance for running Redis
- either a running Portainer instance (preffered), OR knowledge on how to use Docker Compose files.

## Setting up Redis on Portainer
This guide assumes you have Docker already, and will not explain how to setup Docker. We will use Portainer in this guide, but you can always simply use the docker-compose.yml format below instead if you don't wish to use Portainer and know what you are doing.

### 1. Log into your Portainer interface
Click **Live Connect** to connect to your Docker environment, if not connected already.

![portainer1](img/portainer1.PNG)

### 2. Navigate to Custom Templates
Expand **Templates**, then click **Custom**.

![portainer1](img/portainer2.PNG)

### 3. Create a new Custom Template
Click the **+ Add Custom Template** button.

![portainer1](img/portainer3.PNG)

### 4. Configure the Redis Timeseries Template
Fill out the **Title** field and **Description** fields.

![portainer1](img/portainer4.PNG)

### 5. Paste in the Redis Timeserver template code and Save
Copy / Paste the below **Custom Template** code and paste it into the large **Web editor** field on the **Create Custom template** page.
After pasting in, click the **Create Custom Template** button.

**Custom Template Code:** (aka the **docker-compose.yml**)
```
services:
  redistimeseries:
        image: 'redislabs/redistimeseries'
        volumes:
        - redis-data:/data
        - redis-config:/config
        environment:
          - ALLOW_EMPTY_PASSWORD=yes
          - REDIS_CONF_DIR=/config
          - REDIS_DATA_DIR=/data
        ports:
          - 6379:6379

volumes:
  redis-data:
  redis-config:
```

![portainer1](img/portainer5.PNG)
