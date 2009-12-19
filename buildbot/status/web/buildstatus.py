from twisted.web import html, resource
from buildbot.status.web.base import Box
from buildbot.status.web.base import HtmlResource
from buildbot.status.web.base import IBox

class BuildStatusStatusResource(HtmlResource):
    def __init__(self, categories=None):
        HtmlResource.__init__(self)

    def head(self, request):
        return ""

    def content(self, request, ctx):
        """Display a build in the same format as the waterfall page.
        The HTTP GET parameters are the builder name and the build
        number."""

        status = self.getStatus(request)

        # Get the parameters.
        name = request.args.get("builder", [None])[0]
        number = request.args.get("number", [None])[0]
        if not name or not number:
            return "builder and number parameter missing"
        number = int(number)

        # Check if the builder in parameter exists.
        try:
            builder = status.getBuilder(name)
        except:
            return "unknown builder"

        # Check if the build in parameter exists.
        build = builder.getBuild(int(number))
        if not build:
            return "unknown build %s" % number

        rows = ctx['rows'] = []

        # Display each step, starting by the last one.
        for i in range(len(build.getSteps()) - 1, -1, -1):
            if build.getSteps()[i].getText():
                rows.append(IBox(build.getSteps()[i]).getBox(request).td(align="center"))

        # Display the bottom box with the build number in it.
        ctx['build'] = IBox(build).getBox(request).td(align="center")
        
        template = request.site.buildbot_service.templates.get_template("buildstatus.html")
        data = template.render(**ctx)

        # We want all links to display in a new tab/window instead of in the
        # current one.
        # TODO: Move to template
        data = data.replace('<a ', '<a target="_blank"')
        return data
