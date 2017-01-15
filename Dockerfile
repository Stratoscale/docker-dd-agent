FROM debian:jessie

MAINTAINER Datadog <package@datadoghq.com>

ENV DEBIAN_FRONTEND noninteractive
RUN apt-get update && \
    apt-get -y install gcc mono-mcs && \
    apt-get -y install alien dpkg-dev debhelper build-essential && \
    rm -rf /var/lib/apt/lists/*


ENV DOCKER_DD_AGENT=yes \
    AGENT_VERSION=1:5.10.1-1

# Install the Agent
RUN echo "deb http://apt.datadoghq.com/ stable main" > /etc/apt/sources.list.d/datadog.list \
 && apt-key adv --keyserver keyserver.ubuntu.com --recv-keys C7A7DA52 \
 && apt-get update \
 && apt-get install --no-install-recommends -y datadog-agent="${AGENT_VERSION}" \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Configure the Agent
# 1. Listen to statsd from other containers
# 2. Turn syslog off
# 3. Remove dd-agent user from supervisor configuration
# 4. Remove dd-agent user from init.d configuration
# 5. Fix permission on /etc/init.d/datadog-agent
# 6. Remove network check
RUN mv /etc/dd-agent/datadog.conf.example /etc/dd-agent/datadog.conf \
 && sed -i -e"s/^.*non_local_traffic:.*$/non_local_traffic: yes/" /etc/dd-agent/datadog.conf \
 && sed -i -e"s/^.*log_to_syslog:.*$/log_to_syslog: no/" /etc/dd-agent/datadog.conf \
 && sed -i "/user=dd-agent/d" /etc/dd-agent/supervisor.conf \
 && sed -i 's/AGENTUSER="dd-agent"/AGENTUSER="root"/g' /etc/init.d/datadog-agent \
 && chmod +x /etc/init.d/datadog-agent \
 && rm /etc/dd-agent/conf.d/network.yaml.default

# Add Docker check
COPY conf.d/docker_daemon.yaml /etc/dd-agent/conf.d/docker_daemon.yaml

COPY entrypoint.sh /entrypoint.sh

# Extra conf.d and checks.d
VOLUME ["/conf.d", "/checks.d"]

# Expose DogStatsD and supervisord ports
EXPOSE 8125/udp 9001/tcp

COPY requirements.txt /requirements.txt
COPY strato-requirements.txt /strato-requirements.txt
ENV PATH="/opt/datadog-agent/embedded/bin:$PATH"
RUN pip install --upgrade pip
RUN pip install pbr
RUN pip install -r /requirements.txt --extra-index http://strato-pypi.dc1:5001 --trusted-host strato-pypi.dc1
RUN pip install -r /strato-requirements.txt --extra-index http://strato-pypi.dc1:5001 --trusted-host strato-pypi.dc1
RUN pip install --extra-index http://strato-pypi.dc1:5001 --trusted-host strato-pypi.dc1 dr-client
RUN pip install --extra-index http://strato-pypi.dc1:5001 --trusted-host strato-pypi.dc1 dr-manager
COPY build/bring/datalayer_api/strato-datalayer-client-0-1.el7.centos.noarch.rpm /datalayer_client.rpm
RUN alien /datalayer_client.rpm
RUN dpkg -i /datalayer_client.deb strato-datalayer-client_0-2_all.deb
RUN rm -f /datalayer_client.rpm
RUN rm -f /strato-datalayer-client_0-2_all.deb
ENV PYTHONPATH=/usr/share/strato

ENTRYPOINT ["/entrypoint.sh"]
CMD ["supervisord", "-n", "-c", "/etc/dd-agent/supervisor.conf"]
