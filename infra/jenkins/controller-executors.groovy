import jenkins.model.Jenkins

// Builds run on the separate docker-agent, not on the controller.
def controller = Jenkins.get()
controller.setNumExecutors(0)
controller.save()
