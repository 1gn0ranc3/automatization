FROM jenkins/jenkins:2.568.3-jdk21
COPY --chown=jenkins:jenkins plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt
COPY --chown=jenkins:jenkins controller-executors.groovy /usr/share/jenkins/ref/init.groovy.d/controller-executors.groovy
