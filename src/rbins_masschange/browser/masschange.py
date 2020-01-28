#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import re
import traceback

from rbins_masschange.utils import magicstring

import plone.z3cform.templates
import z3c.form
import zope.schema
from OFS.CopySupport import CopyError
from Products.Archetypes.interfaces import IBaseContent
from Products.CMFBibliographyAT.interface.content import IBibliographicItem
from Products.CMFCore.interfaces._content import IFolderish
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.utils import base_hasattr
from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile as FiveViewPageTemplateFile
from Products.statusmessages.interfaces import IStatusMessage
from collective.z3cform.keywordwidget.field import Keywords
from plone import api
from plone.app.dexterity.behaviors.discussion import IAllowDiscussion
from plone.app.dexterity.behaviors.exclfromnav import IExcludeFromNavigation
from plone.app.dexterity.behaviors.metadata import IOwnership
from plone.app.iterate.interfaces import ConflictError
from plone.app.relationfield.behavior import IRelatedItems as BIRelatedItems
from plone.app.textfield.value import RichTextValue
from plone.autoform import directives
from plone.autoform.form import AutoExtensibleForm
from plone.formwidget.masterselect import MasterSelectBoolField
from plone.i18n.normalizer import baseNormalize
from plone.uuid.interfaces import IUUID
from z3c.form.browser import textlines
from z3c.form.browser.checkbox import CheckBoxFieldWidget
from z3c.form.browser.radio import RadioFieldWidget
from z3c.form.interfaces import IFieldWidget
from z3c.form.interfaces import IFormLayer
from z3c.form.util import getSpecification
from z3c.relationfield import RelationValue
from z3c.relationfield.schema import RelationList, RelationChoice
from zope import component, interface
from zope.component import adapter
from zope.i18nmessageid import MessageFactory
from zope.interface import implementer
from zope.intid.interfaces import IIntIds
from zope.schema.vocabulary import SimpleTerm
from zope.schema.vocabulary import SimpleVocabulary
from Products.CMFPlone.utils import safe_unicode

try:
    from plone.app.widgets.interfaces import IWidgetsLayer
    from plone.app.widgets.dx import (RelatedItemsFieldWidget,
                                      AjaxSelectWidget,
                                      RelatedItemsWidget)

    HAS_W = True
except ImportError:
    HAS_W = False
    from plone.formwidget.contenttree import ObjPathSourceBinder

_ = MessageFactory('rbins_masschange')
logger = logging.getLogger('rbins_masschange.masschange')


@adapter(getSpecification(IOwnership['contributors']), IFormLayer)
@implementer(IFieldWidget)
def ContributorsFieldWidget(field, request):
    widget = textlines.TextLinesFieldWidget(field, request)
    return widget


def make_vocabulary(*items):
    terms = [SimpleTerm(value=value, token=value, title=label)
             for value, label in items]
    return SimpleVocabulary(terms)


def safe_encode(s, coding='utf-8', errors='surrogateescape'):
    """encode str to bytes, with round-tripping "invalid" bytes"""
    if s is None:
        return None
    return s.encode(coding, errors)


class IMassChangeSchema(interface.Interface):
    """Define masschange form fields"""
    # directives.widget('local_keywords', InAndOutKeywordWidget)

    overwrite = zope.schema.Bool(
        title=u"Overwrite keywords and contributors",
        required=False,
        default=False,
        description=u"When not selected, you add keywords and contributor to existing ones. When selected, you remove existing values.")

    if not HAS_W:
        selected_obj_paths = RelationList(
            title=u"Objects to change",
            required=True,
            default=[],
            value_type=RelationChoice(
                title=u"Related",
                source=ObjPathSourceBinder()))

        handle_related = MasterSelectBoolField(
            title=u"Handle related items",
            required=False,
            default=False,
            slave_fields=[{
                'name': 'related_obj_paths',
                'action': 'show',
                'hide_values': True,
                'masterSelector': '#form-widgets-handle_related-0',
                'slaveID': '#formfield-form-widgets-related_obj_paths',
            }]
        )

        related_obj_paths = RelationList(
            title=u"Objects to link with",
            required=False,
            default=[],
            value_type=RelationChoice(
                title=u"Link with those objects",
                source=ObjPathSourceBinder()))
    else:
        directives.widget('selected_obj_paths', RelatedItemsWidget)
        directives.widget('related_obj_paths', RelatedItemsWidget)

        selected_obj_paths = RelationList(
            title=u"Objects to change tags",
            required=True,
            default=[],
            value_type=RelationChoice(
                title=u"Related",
                vocabulary="plone.app.vocabularies.Catalog"))

        handle_related = MasterSelectBoolField(
            title=u"Handle related items",
            required=False,
            default=False,
            slave_fields=[{
                'name': 'related_obj_paths',
                'action': 'show',
                'hide_values': True,
                'masterSelector': '#form-widgets-handle_related-0',
                'slaveID': '#formfield-form-widgets-related_obj_paths',
            }])

        related_obj_paths = RelationList(
            title=u"Objects to link with",
            required=False,
            default=[],
            value_type=RelationChoice(
                title=u"Link with those objects",
                vocabulary="plone.app.vocabularies.Catalog"))

    directives.widget(exclude_from_nav=RadioFieldWidget)
    directives.widget(allow_discussion=RadioFieldWidget)
    exclude_from_nav = zope.schema.Bool(
        title=u"Exclude from naviguation",
        required=False,
        default=None,
        description=u"Exclude from naviguation")

    allow_discussion = zope.schema.Bool(
        title=u"Allow comments",
        required=False,
        default=None,
        description=u"Allow comments")

    handle_keywords = MasterSelectBoolField(
        title=u"Handle keywords",
        required=False,
        default=False,
        slave_fields=[{
            'name': 'local_keywords',
            'action': 'show',
            'hide_values': True,
            'masterSelector': '#form-widgets-handle_keywords-0',
            'slaveID': '#formfield-form-widgets-local_keywords',
        }, {
            'name': 'keywords',
            'action': 'show',
            'hide_values': True,
            'masterSelector': '#form-widgets-handle_keywords-0',
            'slaveID': '#formfield-form-widgets-keywords',
        }, {
            'name': 'manual_keywords',
            'action': 'show',
            'hide_values': True,
            'masterSelector': '#form-widgets-handle_keywords-0',
            'slaveID': '#formfield-form-widgets-manual_keywords',
        }]
    )

    local_keywords = zope.schema.List(
        title=u"Keywords from this folder",
        required=False,
        description=u"Keyword (local)",
        value_type=zope.schema.Choice(
            vocabulary='rbins_masschange.localKeywords'))

    keywords = Keywords(
        title=u"keywords",
        description=u"Keyword (general)",
        required=False,
        index_name='Subject')

    manual_keywords = zope.schema.List(
        title=u"Keywords to add", required=False,
        value_type=(zope.schema.TextLine()))

    handle_contributors = MasterSelectBoolField(
        title=u"Handle contributors",
        required=False,
        default=False,
        slave_fields=[{
            'name': 'contributors',
            'action': 'show',
            'hide_values': True,
            'masterSelector': '#form-widgets-handle_contributors-0',
            'slaveID': '#formfield-form-widgets-contributors',
        }]
    )

    contributors = zope.schema.Text(
        title=u"contributors",
        description=u"Contributors (one per line)",
        required=False)

    handle_rights = MasterSelectBoolField(
        title=u"Handle rights",
        required=False,
        default=False,
        slave_fields=[{
            'name': 'rights',
            'action': 'show',
            'hide_values': True,
            'masterSelector': '#form-widgets-handle_rights-0',
            'slaveID': '#formfield-form-widgets-rights',
        }]
    )
    rights = zope.schema.Text(
        title=u"rights",
        description=u"Rights",
        required=False)

    handle_text_replace = MasterSelectBoolField(
        title=u"Replace text",
        required=False,
        default=False,
        slave_fields=[{
            'name': 'text_replace_fields',
            'action': 'show',
            'hide_values': True,
            'masterSelector': '#form-widgets-handle_text_replace-0',
            'slaveID': '#formfield-form-widgets-text_replace_fields',
        }, {
            'name': 'text_replace_mode',
            'action': 'show',
            'hide_values': True,
            'masterSelector': '#form-widgets-handle_text_replace-0',
            'slaveID': '#formfield-form-widgets-text_replace_mode',
        }, {
            'name': 'text_replace_source',
            'action': 'show',
            'hide_values': True,
            'masterSelector': '#form-widgets-handle_text_replace-0',
            'slaveID': '#formfield-form-widgets-text_replace_source',
        }, {
            'name': 'text_replace_destination',
            'action': 'show',
            'hide_values': True,
            'masterSelector': '#form-widgets-handle_text_replace-0',
            'slaveID': '#formfield-form-widgets-text_replace_destination',
        }],
    )

    text_replace_fields = zope.schema.Tuple(
        title=u"Fields to update",
        required=False,
        description=u"Select fields where you want to apply the text replace",
        default=('text',),
        value_type=zope.schema.Choice(
            vocabulary=make_vocabulary(
                (u'text', u"Text body (text)"),
                (u'title', u"Page title (title)"),
                (u'description', u"Description (description)"),
                (u'short-name', u"Short name (id) - not allowed for folders"),
                (u'pdf_url', u"PDF URL (pdf_url)"),
                (u'publication_url', u"Online URL (publication_url)")),
        ))
    directives.widget(text_replace_fields=CheckBoxFieldWidget)

    text_replace_mode = zope.schema.Choice(
        title=u"Text replacement mode",
        required=False,
        description=u"Select fields where you want to apply the text replace",
        default=u'plain',
        vocabulary=make_vocabulary(
            (u'plain', u"Replace plain text by another one"),
            (u'regexp', u"Replace pattern using regular expression."),
            (u'empty', u"Set text on all empty fields."),
        )
    )
    directives.widget(text_replace_mode=RadioFieldWidget)

    text_replace_source = zope.schema.TextLine(
        title=u"Text / pattern to replace",
        description=u"Set the plain text or regular expression to replace. If you choose 'set text on all empty fields', leave this field empty.",
        required=False,
    )

    text_replace_destination = zope.schema.TextLine(
        title=u"Replacement text / pattern",
        required=False,
        description=u"In regular expression mode, you can use \\1, \\2, etc. here to get pattern groups",
    )


def default_keywords(self):
    return self.view.old_keywords[:]


def safe_encode(s, coding='utf-8', errors='surrogateescape'):
    """encode str to bytes, with round-tripping "invalid" bytes"""
    if type(s) == str:
        return s
    elif s is None:
        return None
    else:
        return s.encode(coding, errors)


class MassChangeForm(AutoExtensibleForm, z3c.form.form.Form):
    """ A form to output a HTML masschange from chosen parameters """
    schema = IMassChangeSchema
    ignoreContext = True
    old_keywords = None
    status = ""
    logs = None

    def replace_text(self, item, mode, fields, source, destination):
        changed = False

        def get_new_value(current_value):
            if type(current_value) == str:
                s = safe_encode(source)
                d = safe_encode(destination)
            else:
                s = safe_unicode(source)
                d = safe_unicode(destination)

            if mode == 'plain':
                new_value = current_value.replace(s, d)
            elif mode == 'regexp':
                new_value = re.sub(s, d, current_value)
            elif mode == 'empty':
                new_value = current_value if current_value else d
            else:
                raise ValueError("Unhandled option for text_replace_mode: %s" % mode)
            return new_value

        for field in fields:
            if field == 'short-name':
                continue

            # validation
            if field == 'pdf_url':
                if not IBibliographicItem.providedBy(item):
                    continue

                current = item.pdf_url
                new = get_new_value(current)
                if current != new:
                    item.pdf_url = new
                    changed = True
            elif field == 'publication_url':
                if not IBibliographicItem.providedBy(item):
                    continue

                current = item.publication_url
                new = get_new_value(current)
                if current != new:
                    item.publication_url = new
                    changed = True
            elif field == 'text':
                if IBaseContent.providedBy(item):
                    at_field = item.getField('text')
                    if not at_field:
                        IStatusMessage(self.request).add("%s has no field: %s" % (item.absolute_url(), field), 'error')
                        continue

                    current = at_field.getAccessor(item)()
                    new = get_new_value(current)
                    if current != new:
                        at_field.getMutator(item)(new)
                        changed = True
                elif base_hasattr(item, 'text'):
                    if isinstance(item.text, RichTextValue):
                        current = item.text.raw
                    else:
                        current = item.text

                    new = get_new_value(current)
                    if current != new:
                        if isinstance(item.text, RichTextValue):
                            rtv = item.text
                            rtv._raw_holder.value = new
                            item.text = rtv
                        else:
                            item.text = new
                        changed = True
            elif field == 'title':
                current = item.Title()
                new = get_new_value(current)
                if current != new:
                    item.setTitle(new)
                    changed = True
            elif field == 'description':
                current = item.Description()
                new = get_new_value(current)
                if current != new:
                    item.setDescription(new)
                    changed = True

        if 'short-name' in fields:
            if IFolderish.providedBy(item):
                IStatusMessage(self.request).add('Mass change of short name is forbidden for folder : %s' % item.absolute_url())
            else:
                current = item.id
                new = str(get_new_value(current))
                if current != new:
                    try:
                        api.content.rename(item, new_id=new)
                        changed = True
                    except CopyError:
                        IStatusMessage(self.request).add('Rename failed : %s' % item.absolute_url())
        elif changed:
                item.reindexObject(idxs=['SearchableText'])

        return changed

    def update(self):
        self.old_keywords = []
        try:
            self.old_keywords = [a for a in self.context.Subject()]
        except ConflictError:
            raise
        except Exception:
            pass

        psson = 'paths'
        sson = 'selected_obj_paths'
        obs = []
        pssonvalues = self.request.form.get(psson, [])
        ssonvalues = self.request.form.get(sson, [])
        tp = self.request.form.get('orig_template', '')
        # coming from folder_contents with filters and collections
        if (tp in ['folder_contents'] and
                isinstance(pssonvalues, list) and pssonvalues and
                isinstance(ssonvalues, list) and ssonvalues):
            if isinstance(pssonvalues, list) and pssonvalues:
                for item in pssonvalues:
                    try:
                        v = str(item)
                        self.context.restrictedTraverse(v)
                        obs.append(item)
                    except ConflictError:
                        raise
                    except Exception:
                        pass
        else:
            # coming from folder_contents with filters
            if isinstance(pssonvalues, list) and pssonvalues:
                for item in pssonvalues:
                    try:
                        v = str(item)
                        self.context.restrictedTraverse(v)
                        obs.append(item)
                    except ConflictError:
                        raise
                    except Exception:
                        pass
            # coming from other cases
            elif sson in self.request.form:
                for item in self.request.form[sson]:
                    try:
                        v = str(item)
                        self.context.restrictedTraverse(v)
                        obs.append(item)
                    except ConflictError:
                        raise
                    except Exception:
                        pass
        ret = super(MassChangeForm, self).update()
        if obs:
            if HAS_W:
                portal = getToolByName(self.context,
                                       'portal_url').getPortalObject()
                uids = []
                for i in obs:
                    try:
                        uids.append(IUUID(portal.restrictedTraverse(i)))
                    except ConflictError:
                        raise
                    except Exception:
                        continue
                obs = self.widgets[sson].separator.join(uids)
            self.request.form[u'form.widgets.%s' % sson] = obs
            self.widgets[sson].update()
        return ret

    @z3c.form.button.buttonAndHandler(_(u'Make Changes'), name='masschange')
    def masschange(self, action):
        # already passed (updateWidget called twice
        self.logs, ilogs = [], []
        if self.status != '':
            return
        data, errors = self.extractData()
        if errors:
            self.status = "Please correct errors"
            return
        keywords = []
        for k in 'keywords', 'local_keywords', 'manual_keywords':
            d = data.get(k, None)
            if d:
                [keywords.append(i) for i in d if i not in keywords]
        keywords.sort()

        ctbrs = data['contributors']
        if isinstance(ctbrs, basestring):
            ctbrs = [a.strip() for a in ctbrs.splitlines() if a.strip()]
        if isinstance(ctbrs, (list, tuple)):
            ctbrs = [a for a in ctbrs if a.strip()]

        rights = data['rights']
        if isinstance(rights, basestring) and rights.strip():
            rights = rights.strip()
        else:
            rights = None

        overwrite = data['overwrite']
        exclude_from_nav = data['exclude_from_nav']
        allow_discussion = data['allow_discussion']
        for item in data['selected_obj_paths']:
            changed = False
            if allow_discussion is not None:
                try:
                    ifc = IAllowDiscussion(item)
                    ifc.allow_discussion = allow_discussion
                    changed = True
                except TypeError:
                    # does not handle for now AT based content
                    # try at
                    try:
                        done = False
                        try:
                            item.allowDiscussion(allow_discussion)
                            done = True
                        except ConflictError:
                            raise
                        except Exception:
                            pass
                        try:
                            item.editIsDiscussable(allow_discussion)
                            done = True
                        except ConflictError:
                            raise
                        except Exception:
                            pass
                        if done:
                            item.reindexObject()
                            changed = True
                    except AttributeError:
                        pass
            if exclude_from_nav is not None:
                try:
                    ifc = IExcludeFromNavigation(item)
                    ifc.exclude_from_nav = exclude_from_nav
                    changed = True
                except TypeError:
                    # does not handle for now AT based content
                    # try at
                    try:
                        item.setExcludeFromNav(exclude_from_nav)
                        item.reindexObject()
                        changed = True
                    except AttributeError:
                        pass
            if (ctbrs or rights) and (data['handle_rights'] or data['handle_contributors']):
                try:
                    ownership = IOwnership(item)
                    if rights and data['handle_rights']:
                        ownership.rights = rights
                        changed = True
                    if ctbrs and data['handle_contributors']:
                        if ownership.contributors and not overwrite:
                            for i in ownership.contributors:
                                if i not in ctbrs:
                                    ctbrs.insert(0, i)
                        ownership.contributors = tuple(ctbrs)
                        changed = True
                except TypeError:
                    # does not handle for now AT based content
                    if ctbrs and data['handle_contributors']:
                        # try at
                        try:
                            if item.Contributors() and not overwrite:
                                for i in item.Contributors():
                                    if i not in ctbrs:
                                        ctbrs.insert(0, i)
                            item.setContributors(tuple(ctbrs))
                            changed = True
                        except AttributeError:
                            pass
                    if rights and data['handle_rights']:
                        try:
                            item.Rights
                            item.setRights(rights)
                            changed = True
                        except AttributeError:
                            pass
            ppath = '/'.join(item.getPhysicalPath())
            if data['related_obj_paths'] and data['handle_related']:
                # item support related items
                related = []
                # archetypes
                try:
                    related = item.getRelatedItems()

                    def additem(xxx, related):
                        changed = False
                        xxx = [x for x in xxx if x not in related]
                        if xxx:
                            item.setRelatedItems(related + xxx)
                            changed = True
                        return changed
                except ConflictError:
                    raise
                except Exception:
                    additem = None
                # dexterity
                if not additem:
                    try:
                        related = BIRelatedItems(item).relatedItems

                        def additem(xxx, related):
                            changed = False
                            xxx = [x for x in xxx if x not in related]
                            if True or xxx:
                                intids = component.getUtility(IIntIds)
                                BIRelatedItems(item).relatedItems = (
                                    [RelationValue(intids.getId(obj))
                                     for obj in (related + xxx)])
                                changed = True
                            return changed
                    except ConflictError:
                        raise
                    except Exception:
                        additem = None
                if additem is not None:
                    changed = additem(data['related_obj_paths'], related)
            try:
                oldk = [a for a in self.context.Subject()]
            except ConflictError:
                raise
            except Exception:
                oldk = []
            oldk.sort()
            if (keywords != oldk) and data['handle_keywords']:
                try:
                    try:
                        if item.Subject() and not overwrite:
                            for val in item.Subject():
                                if val not in keywords:
                                    keywords.insert(0, val)
                        item.setSubject(keywords)
                        changed = True
                    except AttributeError:
                        if item.subject and not overwrite:
                            for val in item.subject:
                                if val not in keywords:
                                    keywords.insert(0, val)
                        item.subject = keywords
                        changed = True
                except ConflictError:
                    raise
                except Exception:
                    trace = traceback.format_exc()
                    msg = ('<li>%s %s: cant change keywords '
                           '<br/><pre>%s</pre>\n</li>') % (
                              ppath, keywords, trace)
                    logger.error(msg)
                    ilogs.append(msg)

            if data['handle_text_replace']:
                if self.replace_text(
                        item=item,
                        mode=data['text_replace_mode'],
                        fields=data['text_replace_fields'],
                        destination=data['text_replace_destination'],
                        source=data['text_replace_source']):
                    changed = True

            if changed:
                ilogs.append('<li><a href="%s" target="_new">%s</a> changed</li>\n' % (
                    ppath, item.absolute_url()))
                item.reindexObject()
        if ilogs:
            ilogs.insert(0, u"<strong>MassChange complete</strong>")
            ilogs.insert(0, u"<ul>")
            ilogs.append('</ul>')
        self.logs.extend(ilogs)
        self.logs = '\n'.join(self.logs)


for k in ('keywords', 'local_keywords',):
    component.provideAdapter(
        z3c.form.widget.ComputedWidgetAttribute(
            default_keywords,
            field=IMassChangeSchema[k],
            view=MassChangeForm),
        name="default")

masschange_form_frame = plone.z3cform.layout.wrap_form(
    MassChangeForm,
    index=FiveViewPageTemplateFile("masschange.pt"))


class DeduplicateKeywords(BrowserView):
    def __call__(self, *args, **kwargs):
        catalog = getToolByName(self.context, 'portal_catalog')
        keywords = catalog.uniqueValuesFor(u'Subject')

        normalized_keywords = {}
        for keyword in keywords:
            normalized_keyword = baseNormalize(magicstring(keyword.strip()).decode('utf-8')).strip()
            normalized_keywords.setdefault(normalized_keyword, []).append(keyword)

        pkm = getToolByName(self.context, 'portal_keyword_manager')
        putils = getToolByName(self.context, "plone_utils")
        for normalized_keyword, keywords in normalized_keywords.iteritems():
            if len(keywords) == 1:
                continue
            pkm.change(keywords, normalized_keyword, context=self.context, indexName=u'Subject')
            putils.addPortalMessage(u'Changed {keywords} to {normalized_keyword}'.format(
                    keywords=', '.join(keywords).decode('utf8'),
                    normalized_keyword=normalized_keyword.decode('utf8')
                ),
                type='info',
            )

        return self.request.response.redirect(self.context.absolute_url())


# vim:set et sts=4 ts=4 tw=80:
