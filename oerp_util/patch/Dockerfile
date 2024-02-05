FROM ubuntu:jammy

# basic configuration

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Europe/Berlin


# configure default locale

RUN apt-get clean && apt-get update && apt-get install -y locales && \
    locale-gen de_DE.UTF-8 && \
    echo 'LANG="de_DE.UTF-8"' > /etc/default/locale && \
    update-locale LANG=de_DE.UTF-8


# install os python dependencies

RUN apt-get install -y -f \
    fonts-dejavu-core \
    fonts-freefont-ttf \
    fonts-freefont-otf \
    fonts-noto-core \
    fonts-inconsolata \
    fonts-font-awesome \
    fonts-roboto-unhinted \
    fonts-ubuntu \
    libfontenc1 xfonts-75dpi xfonts-base xfonts-encodings xfonts-utils \
    gsfonts \
    libjs-underscore \
    lsb-base \
    postgresql-client \
    python3-babel \
    python3-chardet \
    python3-dateutil \
    python3-decorator \
    python3-docutils \
    python3-freezegun \
    python3-geoip2 \
    python3-pil \
    python3-jinja2 \
    python3-libsass \
    python3-lxml \
    python3-num2words \
    python3-ofxparse \
    python3-passlib \
    python3-polib \
    python3-psutil \
    python3-psycopg2 \
    python3-pydot \
    python3-openssl \
    python3-pypdf2 \
    python3-rjsmin \
    python3-qrcode \
    python3-renderpm \
    python3-reportlab \
    python3-requests \
    python3-stdnum \
    python3-tz \
    python3-vobject \
    python3-werkzeug \
    python3-xlsxwriter \
    python3-xlrd \
    python3-zeep \
    python3-ldap \
    python3-gevent \
    python3-greenlet \
    python3-idna \
    python3-markupsafe \
    python3-pillow \
    python3-serial \
    python3-usb \
    python3-urllib3 \
    python3-xlwt \
    python3-yaml \
    python3-pdfminer \
    python3-google-auth \
    python3-pip

# install whktmltopdf
COPY docker/install /install
RUN dpkg -i /install/wkhtmltox_0.12.6.1-2.jammy_amd64.deb ; apt-get install -f -y

# fix imagemagick policy
COPY docker/files/ImageMagick-6/policy.xml /etc/ImageMagick-6/policy.xml

# install entrypoint
COPY docker/files/odoo /usr/local/bin/odoo

# setup odoo
RUN useradd -ms /bin/bash odoo
RUN mkdir /data
RUN chown 1000:1000 /data

# setup additional requirements
# COPY requirements.txt /home/odoo/requirements.txt
# RUN pip install pip
# RUN pip install -r /home/odoo/requirements.txt

# switch to odoo user
USER odoo
WORKDIR /home/odoo
RUN mkdir /data/etc
RUN mkdir /data/filestore
RUN mkdir /data/log
RUN mkdir /data/sessions

# copy odoo source
COPY odoo /home/odoo/odoo

# switch to root and cleanup
USER root
RUN rm -rf /install
RUN apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# expose
EXPOSE 8069 8072

# volumes
VOLUME ["/data"]

# basic entrypoint with user odoo
USER odoo
ENTRYPOINT ["/usr/local/bin/odoo"]
CMD ["serve"]
