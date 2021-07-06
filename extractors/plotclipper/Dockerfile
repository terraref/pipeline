FROM terraref/terrautils:1.5
MAINTAINER Max Burnette <mburnet2@illinois.edu>

# Install any programs needed
RUN useradd -u 49044 extractor \
    && mkdir /home/extractor \
    && mkdir /home/extractor/sites

RUN chown -R extractor /home/extractor \
    && chgrp -R extractor /home/extractor 

# Install PDAL
RUN apt-get update \
    && apt-get install -y pdal \
        imagemagick \
        gdal-bin \
        libgdal-dev

# Install laser3d science package
RUN pip install --upgrade pip 
RUN pip install wheel laspy multiprocess plyfile \
    && pip install --upgrade pyclowder \
    && pip install --upgrade terraref-laser3d \
    && pip install --upgrade cryptography

# command to run when starting docker
COPY entrypoint.sh extractor_info.json *.py /home/extractor/

USER extractor
ENTRYPOINT ["/home/extractor/entrypoint.sh"]
CMD ["extractor"]

# Setup environment variables. These are passed into the container. You can change
# these to your setup. If RABBITMQ_URI is not set, it will try and use the rabbitmq
# server that is linked into the container. MAIN_SCRIPT is set to the script to be
# executed by entrypoint.sh
ENV RABBITMQ_EXCHANGE="terra" \
    RABBITMQ_VHOST="%2F" \
    RABBITMQ_QUEUE="terra.plotclipper" \
    MAIN_SCRIPT="terra_plotclipper.py"
