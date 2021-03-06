
from urllib.request import urlopen
from xml.dom.minidom import parseString

from braces.views import FormMessagesMixin, PermissionRequiredMixin
from django.core.urlresolvers import reverse_lazy
from django.db.models import Q
from django.http.response import HttpResponse
from django.utils.translation import ugettext_lazy as _
from django.views.generic.base import View, TemplateView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, FormView,\
    FormMixin
from django.views.generic.list import ListView

from core import forms
from core.cifra import Cifrador
from core.models import Classe, Musica, MusicaHistory, VersaoHistory, Versao
from musicat.utils import make_pagination


class ClasseListView(PermissionRequiredMixin, ListView):
    model = Classe
    permission_required = 'core.list_classe'
    raise_exception = True

    paginate_by = 10
    verbose_name = model._meta.verbose_name
    verbose_name_plural = model._meta.verbose_name_plural

    def get_context_data(self, **kwargs):
        context = super(ListView, self).get_context_data(**kwargs)
        context.setdefault('title', self.verbose_name_plural)

        paginator = context['paginator']
        page_obj = context['page_obj']
        context['page_range'] = make_pagination(
            page_obj.number, paginator.num_pages)
        return context

    @property
    def create_url(self):
        return reverse_lazy('core:classe_create')


class ClasseCreateView(PermissionRequiredMixin, FormMessagesMixin, CreateView):
    model = Classe
    permission_required = 'core.add_classe'
    raise_exception = True
    template_name = 'crud/form.html'

    form_valid_message = _('Classe criada com sucesso!')
    form_invalid_message = _('Existem erros no formulário!')
    form_class = forms.ClasseForm

    @property
    def cancel_url(self):
        return reverse_lazy('core:classe_list')

    def get_success_url(self):
        return reverse_lazy('core:classe_change',
                            kwargs={'pk': self.object.pk})


class ClasseUpdateView(PermissionRequiredMixin, FormMessagesMixin, UpdateView):
    model = Classe
    permission_required = 'core.change_classe'
    raise_exception = True
    template_name = 'crud/form.html'

    form_valid_message = _('Classe alterada com sucesso!')
    form_invalid_message = _('Existem erros no formulário!')
    form_class = forms.ClasseForm

    @property
    def cancel_url(self):
        return reverse_lazy('core:classe_list')

    def get_success_url(self):
        return reverse_lazy('core:classe_change',
                            kwargs={'pk': self.kwargs['pk']})


class MusicaImportView(View):

    def get(self, request, *args, **kwargs):
        from django.db import connection
        #file = urlopen('http://musicat.com.br/xml/export')
        file = open('/home/leandro/TEMP/musicat.import')
        data = file.read()
        file.close()
        xmldoc = parseString(data)

        rootNode = xmldoc.firstChild

        musicas = rootNode.getElementsByTagName('musica')

        cursor = connection.cursor()
        cursor.execute("delete from core_versaohistory")
        cursor.execute("delete from core_versao")
        cursor.execute("delete from core_musicahistory_classes")
        cursor.execute("delete from core_musicahistory")
        cursor.execute("delete from core_musica")
        cursor.close()

        for m in musicas:

            musica = Musica()
            for child in m.childNodes:
                if not len(child.childNodes):
                    continue
                # if child.tagName == 'id':
                #    musica.pk = child.firstChild.nodeValue
                if child.tagName == 'url':
                    musica.uri = child.firstChild.nodeValue
                if child.tagName == 'titulo':
                    musica.titulo = child.firstChild.nodeValue
            musica.save()

            mh = MusicaHistory()
            mh.musica = musica
            mh.modifier = request.user
            mh.titulo = musica.titulo
            mh.save()

            for child in m.childNodes:
                if not len(child.childNodes):
                    continue
                elif child.tagName == 'classificacoes':
                    classes = child.getElementsByTagName('id')
                    for cls in classes:
                        classe_id = cls.firstChild.nodeValue
                        classe = Classe.objects.get(pk=classe_id)
                        mh.classes.add(classe)
                elif child.tagName == 'versoes':
                    versaos = child.getElementsByTagName('versao')
                    for versao in versaos:

                        v = Versao()
                        v.musica = musica
                        v.save()

                        vh = VersaoHistory()
                        vh.versao = v
                        vh.modifier = request.user
                        vh.save()

                        for vc in versao.childNodes:
                            if not len(vc.childNodes):
                                continue
                            if vc.tagName == 'descr':
                                vh.descr = vc.firstChild.nodeValue
                            elif vc.tagName == 'texto':
                                vh.texto = vc.firstChild.nodeValue

                        vh.save()

            mh.save()

        return HttpResponse('ok', content_type='text/plain; charset=utf8')


class MusicaListView(ListView):
    model = Musica

    paginate_by = 100
    verbose_name_plural = ''

    def get(self, request, *args, **kwargs):
        return super(ListView, self).get(request, *args, **kwargs)

    def get_queryset(self):

        search = ''
        if 'search' in self.request.GET:
            search = self.request.GET['search']

        if not search:
            return ListView.get_queryset(self)

        q = Q()
        texto = search.split(' ')

        for item in texto:
            if not item:
                continue
            q = q & (
                Q(titulo__icontains=item) |
                Q(versoes_set__historico_versao_set__texto__icontains=item) |
                Q(versoes_set__historico_versao_set__descr__icontains=item)
            )

        return Musica.objects.filter(q).order_by('uri').distinct('uri')

    def get_context_data(self, **kwargs):
        context = super(ListView, self).get_context_data(**kwargs)
        context.setdefault('title', self.verbose_name_plural)

        paginator = context['paginator']
        page_obj = context['page_obj']
        context['page_range'] = make_pagination(
            page_obj.number, paginator.num_pages)
        return context

    @property
    def create_url(self):
        return reverse_lazy('core:musica_list')


class MusicaDetailView(DetailView):
    model = Musica
    slug_field = 'uri'

    @property
    def update_url(self):
        return reverse_lazy('core:musica_list')

    def get_context_data(self, **kwargs):
        context = super(MusicaDetailView, self).get_context_data(**kwargs)

        if not self.kwargs['versao_id']:
            versao = self.object.versoes_set.first(
            ).historico_versao_set.first()
        else:
            try:
                versao = self.object.versoes_set.get(
                    pk=self.kwargs['versao_id']).historico_versao_set.first(
                )
            except:
                versao = self.object.versoes_set.first(
                ).historico_versao_set.first()

        direcao = 0
        if 'direcao' in self.request.GET:
            direcao = int(self.request.GET['direcao'])

        if direcao and 'versao_session' in self.request.session:
            versao_session = self.request.session['versao_session']

            if versao_session.pk == versao.pk:
                versao = versao_session

        cifrador = Cifrador(versao.texto)

        cifra = cifrador.run(direcao)

        novo_texto = '\r\n'.join([c[2] for c in cifra])
        versao.texto = novo_texto

        if direcao:
            self.request.session['versao_session'] = versao

        context.setdefault('cifra', cifra)
        context.setdefault('tom', cifrador.tom)
        context.setdefault('versao_ativa', versao.pk)
        return context

    def get(self, request, *args, **kwargs):
        if 'action' in request.GET:
            self.template_name_suffix = '_detail_ajax'
        else:
            self.template_name_suffix = '_detail'

        return super(DetailView, self).get(request, *args, **kwargs)
