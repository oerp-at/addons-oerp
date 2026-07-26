FROM ubuntu:26.04

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
    gzip \
    rsync \
    restic \
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
    liburing2 \
    libseccomp2 \
    libunwind8 \
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
    python3-lxml-html-clean \
    python3-num2words \
    python3-ofxparse \
    python3-passlib \
    python3-polib \
    python3-psutil \
    python3-psycopg2 \
    python3-pydot \
    python3-openssl \
    python3-pypdf \
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
    python3-tabulate \
    python3-pip \
    python3-phonenumbers \
    python3-json5 \
    python3-websocket \
    python3-cbor2 \
    python3-asn1crypto \
    python3-openpyxl \
    python3-behave \
    python3-magic \
    python3-h11

# install wkhtmltopdf (no build for ubuntu > jammy, the jammy build works fine)
COPY docker/install /install
RUN dpkg -i /install/wkhtmltox_0.12.6.1-2.jammy_amd64.deb ; apt-get install -f -y

# install paper-muncher (long term replacement for wkhtmltopdf)
# --force-depends: the deb declares "liburing" and "libunwind" which are not
# real package names on ubuntu; the actual libs (liburing2, libseccomp2,
# libunwind8) are installed above
RUN dpkg -i --force-depends /install/paper-muncher_v0.6.0_plucky_amd64.deb
ENV PATH="/opt/paper-muncher/bin:${PATH}"

# fix imagemagick policy
COPY docker/files/ImageMagick-6/policy.xml /etc/ImageMagick-6/policy.xml

# install entrypoint
COPY docker/files/odoo /usr/local/bin/odoo

# setup odoo
# ubuntu base images >= 23.10 ship a default "ubuntu" user with uid 1000,
# remove it so odoo gets uid 1000 (matches /data ownership and volumes)
RUN userdel -r ubuntu && useradd -ms /bin/bash -u 1000 odoo
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
COPY addons-design-themes /home/odoo/addons-design-themes
COPY addons-oerp /home/odoo/addons-oerp
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
