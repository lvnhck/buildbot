from __future__ import generators

import sys, time, os.path
import urllib

from twisted.web import html, resource

from buildbot import util
from buildbot import version
from buildbot.status.web.base import HtmlResource
#from buildbot.status.web.base import Box, HtmlResource, IBox, ICurrentBox, \
#     ITopBox, td, build_get_class, path_to_build, path_to_step, map_branches
from buildbot.status.web.base import build_get_class

# set grid_css to the full pathname of the css file
if hasattr(sys, "frozen"):
    # all 'data' files are in the directory of our executable
    here = os.path.dirname(sys.executable)
    grid_css = os.path.abspath(os.path.join(here, "grid.css"))
else:
    # running from source; look for a sibling to __file__
    up = os.path.dirname
    grid_css = os.path.abspath(os.path.join(up(__file__), "grid.css"))

class ANYBRANCH: pass # a flag value, used below

class GridStatusMixin(object):
    def getTitle(self, request):
        status = self.getStatus(request)
        p = status.getProjectName()
        if p:
            return "BuildBot: %s" % p
        else:
            return "BuildBot"

    def getChangemaster(self, request):
        # TODO: this wants to go away, access it through IStatus
        return request.site.buildbot_service.getChangeSvc()

    # handle reloads through an http header
    # TODO: send this as a real header, rather than a tag
    def get_reload_time(self, request):
        if "reload" in request.args:
            try:
                reload_time = int(request.args["reload"][0])
                return max(reload_time, 15)
            except ValueError:
                pass
        return None

    def head(self, request):
        head = ''
        reload_time = self.get_reload_time(request)
        if reload_time is not None:
            head += '<meta http-equiv="refresh" content="%d">\n' % reload_time
        return head

    def build_cxt(self, request, build):
        if not build:
            return {}

        if build.isFinished():
            # get the text and annotate the first line with a link
            text = build.getText()
            if not text: text = [ "(no information)" ]
            if text == [ "build", "successful" ]: text = [ "OK" ]
        else:
            text = [ 'building' ]

        name = build.getBuilder().getName()
        number = build.getNumber()

        cxt = {}
        cxt['name'] = name
        cxt['url'] = "builders/%s/builds/%d" % (name, number)
        cxt['text'] = text
        cxt['class'] = build_get_class(build)
        return cxt

    def builder_cxt(self, request, builder):
        state, builds = builder.getState()

        # look for upcoming builds. We say the state is "waiting" if the
        # builder is otherwise idle and there is a scheduler which tells us a
        # build will be performed some time in the near future. TODO: this
        # functionality used to be in BuilderStatus.. maybe this code should
        # be merged back into it.
        upcoming = []
        builderName = builder.getName()
        for s in self.getStatus(request).getSchedulers():
            if builderName in s.listBuilderNames():
                upcoming.extend(s.getPendingBuildTimes())
        if state == "idle" and upcoming:
            state = "waiting"

        # TODO: for now, this pending/upcoming stuff is in the "current
        # activity" box, but really it should go into a "next activity" row
        # instead. The only times it should show up in "current activity" is
        # when the builder is otherwise idle.

        cxt = { 'url': urllib.quote(builder.getName(), safe=''),
                'name': builder.getName(),
                'state': state,
                'n_pending': len(builder.getPendingBuilds()) }

        return cxt

    def getRecentSourcestamps(self, status, numBuilds, categories, branch):
        """
        get a list of the most recent NUMBUILDS SourceStamp tuples, sorted
        by the earliest start we've seen for them
        """
        # TODO: use baseweb's getLastNBuilds?
        sourcestamps = { } # { ss-tuple : earliest time }
        for bn in status.getBuilderNames():
            builder = status.getBuilder(bn)
            if categories and builder.category not in categories:
                continue
            build = builder.getBuild(-1)
            while build:
                ss = build.getSourceStamp(absolute=True)
                start = build.getTimes()[0]
                build = build.getPreviousBuild()

                # skip un-started builds
                if not start: continue

                # skip non-matching branches
                if branch != ANYBRANCH and ss.branch != branch: continue

                sourcestamps[ss] = min(sourcestamps.get(ss, sys.maxint), start)

        # now sort those and take the NUMBUILDS most recent
        sourcestamps = sourcestamps.items()
        sourcestamps.sort(lambda x, y: cmp(x[1], y[1]))
        sourcestamps = map(lambda tup : tup[0], sourcestamps)
        sourcestamps = sourcestamps[-numBuilds:]

        return sourcestamps

class GridStatusResource(HtmlResource, GridStatusMixin):
    # TODO: docs
    status = None
    control = None
    changemaster = None

    def __init__(self, allowForce=True, css=None):
        HtmlResource.__init__(self)

        self.allowForce = allowForce
        self.css = css or grid_css


    def body(self, request):
        """This method builds the regular grid display.
        That is, build stamps across the top, build hosts down the left side
        """

        # get url parameters
        numBuilds = int(request.args.get("width", [5])[0])
        categories = request.args.get("category", [])
        branch = request.args.get("branch", [ANYBRANCH])[0]
        if branch == 'trunk': branch = None

        # and the data we want to render
        status = self.getStatus(request)
        stamps = self.getRecentSourcestamps(status, numBuilds, categories, branch)

        cxt = {'project_url': status.getProjectURL(),
               'project_name': status.getProjectName(),
               'categories': categories,
               'branch': branch,
               'ANYBRANCH': ANYBRANCH,
               'stamps': stamps,
              }  
            html_categories = map(html.escape(categories))
        
        sortedBuilderNames = status.getBuilderNames()[:]
        sortedBuilderNames.sort()
        
        cxt['builders'] = []

        for bn in sortedBuilderNames:
            builds = [None] * len(stamps)

            builder = status.getBuilder(bn)
            if categories and builder.category not in categories:
                continue

            build = builder.getBuild(-1)
            while build and None in builds:
                ss = build.getSourceStamp(absolute=True)
                for i in range(len(stamps)):
                    if ss == stamps[i] and builds[i] is None:
                        builds[i] = build
                build = build.getPreviousBuild()

            b = self.builder_cxt(request, builder)
            b['builds'] = []
            for build in builds:
                b['builds'].append(self.build_cxt(request, build))

            cxt['builders'].append(b)

        template = request.site.buildbot_service.templates.get_template("grid.html")
        data = template.render(**cxt)
        data += self.footer(request)        
        return data

class TransposedGridStatusResource(HtmlResource, GridStatusMixin):
    # TODO: docs
    status = None
    control = None
    changemaster = None

    def __init__(self, allowForce=True, css=None):
        HtmlResource.__init__(self)

        self.allowForce = allowForce
        self.css = css or grid_css


    def body(self, request):
        """This method builds the transposed grid display.
        That is, build hosts across the top, build stamps down the left side
        """

        # get url parameters
        numBuilds = int(request.args.get("length", [5])[0])
        categories = request.args.get("category", [])
        branch = request.args.get("branch", [ANYBRANCH])[0]
        if branch == 'trunk': branch = None

        # and the data we want to render
        status = self.getStatus(request)
        stamps = self.getRecentSourcestamps(status, numBuilds, categories, branch)

        cxt = {'project_url': status.getProjectURL(),
               'project_name': status.getProjectName(),
               'categories': categories,
               'branch': branch,
               'ANYBRANCH': ANYBRANCH,
               'stamps': stamps,
              }          
            html_categories = map(html.escape(categories))

        sortedBuilderNames = status.getBuilderNames()[:]
        sortedBuilderNames.sort()
        
        cxt['sorted_builder_names'] = sortedBuilderNames
        cxt['builder_builds'] = builder_builds = {}
        cxt['builders'] = builders = []
        cxt['range'] = range(len(stamps))

        for bn in sortedBuilderNames:
            builds = [None] * len(stamps)

            builder = status.getBuilder(bn)
            if categories and builder.category not in categories:
                continue

            build = builder.getBuild(-1)
            while build and None in builds:
                ss = build.getSourceStamp(absolute=True)
                for i in range(len(stamps)):
                    if ss == stamps[i] and builds[i] is None:
                        builds[i] = build
                build = build.getPreviousBuild()

            builders.append(self.builder_cxt(request, builder))
            builder_builds[bn] = map(lambda b: self.build_cxt(request, b), builds)

        template = request.site.buildbot_service.templates.get_template('grid_transposed.html')
        data = template.render(**cxt)
        data += self.footer(request)        
        return data

