FROM tensorflow/tensorflow:2.9.1-jupyter

# create unprivileged user for container, make directories
RUN adduser --disabled-password --gecos "App" app && \
     mkdir -p /home/app/src && \
     mkdir -p /home/app/work && \
		 mkdir -p /home/app/bin

# set ownership of everything
RUN chown -R app:app /home/app

RUN apt-get update && \
    apt-get install emacs -y && \
    rm -rf /var/lib/apt/lists/*

# Switch to unprivileged user
USER app

# add path used by pip to PATH
ENV PATH $PATH:/home/app/.local/bin

WORKDIR /home/app

ADD --chown=app:app . /home/app/bifrost
RUN  pip install --user -e /home/app/bifrost/
