#!/usr/bin/env python3
#-*- coding: utf-8 -*-

#%%
# import
# import
import os
from datetime import datetime as dt
from typing import Counter, Optional, List, Dict, ClassVar, Final
from dataclasses import dataclass, field
import requests
import numpy as np
import pandas as pd
import asn1tools
from ratelimiter import RateLimiter
import wget
import tqdm
from pathlib import Path
from multiprocessing.pool import ThreadPool as Pool

#%% 
# constants
ASN1_PATHS = [ 
    r'class_descriptors/bu.asn1', 
    r'class_descriptors/rdv.asn1', 
    r'class_descriptors/assinatura.asn1' 
]
BU_ROOTDIR = Path(r"../eleicoes/")
REQ_MAX_CALLS = 10
REQ_PERIOD = 1

#%%
# requests rate limiter
@RateLimiter(max_calls = REQ_MAX_CALLS, period = REQ_PERIOD)
def get_rl(*args, **kwargs):
    return requests.get(*args, **kwargs)

# function to download concurrently
# https://stackoverflow.com/questions/52000950/python-wget-download-multiple-files-at-once
def wget_download_async(
    url: str,
    dl_file: Path,
    vm = None
) -> None:
    wget.download(
        url = url,
        out = str(dl_file)
    )

    if vm is not None:
        vm.caminho_bu = dl_file
        vm.stale_data = False

#%%
# dataclasses
@dataclass
class Contest:
    year: int
    contest_id: int


@dataclass
class Election:
    id: int
    contest: Contest

@dataclass
class Country:
    name: str

@dataclass
class Region:
    name: str = field(compare = False)
    abbr: str
    country: Country
    regions: ClassVar[list] = []

    def __post_init__(self):
        self.regions.append(self)


@dataclass
class State:
    name: str = field(compare = False)
    abbr: str
    region: Region = field(compare = False)
    states: ClassVar[list] = []

    def __post_init__(self):
        self.states.append(self)

    def get_url_votos(self, ano: int, eleicao: int, cargo: str, estado: Optional[str] = None) -> str:
        """gera URL JSON com quantitativos de votação para cada regiao.
        Ex. de URL: 'https://resultados.tse.jus.br/oficial/ele2022/546/dados-simplificados/rj/rj-c0007-e000546-r.json'

        Args:
            ano (int): ano da eleição
            eleicao (int): número da eleição
            regiao (str): código de 2 caract de cada estado do brasil, ou 'br' para o brasil como todo
            cargo (str): cargo sendo disputado ('presidente', 'governador', 'senador', 'deputado federal', 'prefeito', 'vereador', 'deputado estadual')

        Returns:
            str: url
        """

        base = rf'https://resultados.tse.jus.br/oficial'

        if estado is None:
            estado = self.abbr.lower()

        url_ano = f'ele{ano}'
        url_eleicao_simples = str(eleicao)
        url_eleicao_p = f'e{url_eleicao_simples:0>6s}'
        url_estado = str(estado).lower()
        
        id_cargos = {
            'presidente': 1,
            'governador': 3,
            'senador': 5,
            'deputado federal': 6,
            'deputado estadual': 7,
            'deputado distrital': 8,
        }

        id_cargo = id_cargos[cargo.lower()]
        url_cargo = f'c{str(id_cargo):0>4s}'

        url_final = rf'{base}/{url_ano}/{url_eleicao_simples}/dados-simplificados/{url_estado}/{url_estado}-{url_cargo}-{url_eleicao_p}-r.json'

        return url_final

    def get_url_info_mun_zona_secao(self, ano: int, pleito: int, estado: Optional[str] = None) -> str:
        """gera URL JSON com informações sobre municípios, zonas e seções eleitorais.
        Ex de URL: 'https://resultados.tse.jus.br/oficial/ele2022/arquivo-urna/406/config/rj/rj-p000406-cs.json'

        Args:
            ano (int): ano do pleito
            pleito (int): número do pleito
            regiao (str): código de 2 caract de cada estado do brasil ('br' é ilegal nessa URL)

        Returns:
            str: url
        """

        base = rf'https://resultados.tse.jus.br/oficial'

        if estado is None:
            estado = self.abbr.lower()
        
        url_ano = f'ele{ano}'
        
        url_pleito_simples = str(pleito)
        url_pleito_p = f'p{url_pleito_simples:0>6s}'

        url_estado = str(estado).lower()

        url_final = rf'{base}/{url_ano}/arquivo-urna/{url_pleito_simples}/config/{url_estado}/{url_estado}-{url_pleito_p}-cs.json'
        
        return url_final
    
    def process_info_mun_zona_secao(self, ano: int, pleito: int) -> list[dict]:
        
        pleito_obj = Contest(year = ano, contest_id = pleito)

        url = self.get_url_info_mun_zona_secao(
            ano = pleito_obj.year, 
            pleito = pleito_obj.contest_id, 
            estado = self.abbr
        )
        restapi = get_rl(url)
        jsondata = restapi.json()

        municipios = {}
        zonas = {}
        secoes = {}
        
        estado_abbr = jsondata['abr'][0]['cd']
        for municipio in jsondata['abr'][0]['mu']:
            
            id_municipio = int(municipio['cd'])
            municipio_obj = City(
                id = id_municipio,
                name = municipio['nm'],
                state = self
            )

            municipios[id_municipio] = municipio_obj

            for zona in municipio['zon']:
                
                zona_id = int(zona['cd'])
                zona_obj = ElectionZone(
                    id = zona_id,
                    city = municipio_obj
                )

                zonas[f'{str(id_municipio):0>5s}{str(zona_id):0>4s}'] = zona_obj

                for secao in zona['sec']:

                    secao_id = int(secao['ns'])
                    secao_obj = ElectionSection(
                        id = secao_id,
                        zone = zona_obj,
                        contest = pleito_obj
                    )
                    urna_obj = VotingMachine(section = secao_obj)

                    secoes[f'{str(id_municipio):0>5s}{str(zona_id):0>4s}{str(secao_id):0>4s}'] = secao_obj
        
        return municipios, zonas, secoes

    def __str__(self):
        return f'{self.name} ({self.abbr})'


@dataclass
class City:
    id: int
    name: str = field(compare = False)
    state: State = field(compare = False)

    def __str__(self):
        id_municipio = str(self.id)
        nome_municipio = self.name
        abbr_estado = self.state.abbr
        return f'{nome_municipio}, {abbr_estado} (Cód. {id_municipio:0>5s})'


@dataclass
class PartyFederation:
    name: str

    def __str__(self):
        return f'{self.name}'


@dataclass
class Party:
    number: int
    name: str = field(compare = False)
    federation: Optional[PartyFederation] = field(compare = False, default = None)
    all_parties: ClassVar[list] = []

    def __post_init__(self):
        self.__class__.all_parties.append(self)
    
    def __str__(self):
        ret = f'{self.name} ({self.number})'
        if self.federation is not None:
            ret += f' ({str(self.federation)})'
        
        return ret


@dataclass
class Candidate:
    job: str
    number: int
    domain: Country | State | City
    party: Party
    name: str = field(compare = False)

    def __str__(self):
        if isinstance(self.domain, Country):
            domain_name = ''
        elif isinstance(self.domain, State):
            domain_name = f'/{str(self.state.abbr)}'
        else:
            domain_name = f'/{str(self.state.city)}'
        return f'{self.name} - {self.job}{domain_name} #{self.number} ({self.party.name})'


@dataclass
class VoteCount:
    candidate: Candidate
    votes: int


@dataclass
class ElectionZone:
    id: int
    city: City

    def __str__(self):
        id_municipio = str(self.city.id)
        nome_municipio = self.city.name
        abbr_estado = self.city.state.abbr
        zona = str(self.id)
        return f'{nome_municipio}, {abbr_estado} (Cód. {id_municipio:0>5s}), zona {zona:0>4s}'


@dataclass
class ElectionSection:
    id: int
    zone: ElectionZone
    contest: Contest

    def __str__(self):
        id_municipio = str(self.zone.city.id)
        nome_municipio = self.zone.city.name
        abbr_estado = self.zone.city.state.abbr
        zona = str(self.zone.id)
        secao = str(self.id)
        ret = f'{nome_municipio}, {abbr_estado} (Cód. {id_municipio:0>5s}), zona {zona:0>4s}, seção {secao:0>4s}'
        ret += f', pleito {self.contest.contest_id} ({self.contest.year})'


@dataclass
class VotingMachine:
    section: ElectionSection
    serial: Optional[str] = field(compare = False, default = None)
    caminho_bu: Optional[Path] = field(compare = False, default = None)
    envelope_urna: Optional[Dict] = field(compare = False, default = None)
    boletim_urna: Optional[Dict] = field(compare = False, default = None)
    stale_data: bool = field(compare = False, default = True)
    hash_urna: Optional[str] = field(compare = False, default = None)
    hash_dt: Optional[dt] = field(compare = False, default = dt(1970,1,1,0,0,0))
    all_vms: ClassVar[list] = []

    def __post_init__(self):
        self.__class__.all_vms.append(self)
    
    # https://stackoverflow.com/questions/52000950/python-wget-download-multiple-files-at-once
    @classmethod
    def download_multiple_bu(cls, 
        vms: Optional[list] = None,
        caminho_dl_root: Optional[Path] = None,
        progressbar: bool = True
    ):
        if progressbar:
            pb_collect = lambda iter: tqdm.tqdm(iter, desc = 'Collecting URLs and creating folder structure')
            pb_download = lambda iter: tqdm.tqdm(iter, desc = 'Downloading')
            pb_process = lambda iter: tqdm.tqdm(iter, desc = 'Processing')
        else:
            pb_collect = lambda iter: iter
            pb_download = lambda iter: iter
            pb_process = lambda iter: iter
        
        if vms is None:
            vms = VotingMachine.all_vms


        wget_download_list = []

        for vm in pb_collect(vms):
            url_dl = vm.get_info_download_url()

            caminho_dl = vm.get_info_download_path(caminho_dl_root)

            try:
                caminho_dl.mkdir(mode = 0o774, parents = True, exist_ok = True)
            except FileExistsError:
                pass
            

            bu_path = caminho_dl.joinpath(Path(Path(url_dl).name))
            
            if bu_path.exists():
                bu_path.unlink()
            
            wget_download_list.append([
                url_dl,
                bu_path,
                vm
            ])

        with Pool(processes = len(vms)) as pool:
            
            jobs = []
            for url, bu_path, vm in wget_download_list:
                jobs.append(
                    pool.apply_async(
                        func = wget_download_async,
                        args = (url, str(bu_path), vm,)
                    )
                )
            
            pool.close()

            result_list_tqdm = []
            for job in pb_download(jobs):
                result_list_tqdm.append(job.get())
        
        for vm in pb_process(vms):
            vm.envelope_urna, vm.boletim_urna = vm.processa_bu()
            vm.stale_data = False

    def check_data_staleness(self, 
        bu_path: Optional[Path] = None, 
        dtfmt: Optional[str] = None
    ) -> bool:
       
        if self.boletim_urna is None:
            return True
        
        # data e hora no boletim de urna local
        if self.hash_dt is None:
            return True
        else:
            dt_hash_local = self.hash_dt

        # data e hora informados pela API do TSE
        url_info = self.get_url_info_urna()
        restapi = get_rl(url_info)
        jsondata = restapi.json()

        _, dt_hash_remoto = self.get_hash_dtrefresh(
            hashdict = jsondata['hashes'][0],
            dtfmt = dtfmt
        )
        
        if dt_hash_remoto > dt_hash_local:
            return True
        else:
            return False

    def get_url_info_urna(self, 
        ano: Optional[int] = None, pleito: Optional[int] = None, 
        regiao: Optional[str] = None, 
        id_municipio: Optional[int] = None, zona: Optional[int] = None, secao: Optional[int] = None
    ):
        """gera URL JSON com instruções de download de arquivos relacionados à apuração de cada urna individual, a saber: boletim de urna, registro digital de voto e log de urna.
        Ex. de URL: 'https://resultados.tse.jus.br/oficial/ele2022/arquivo-urna/406/dados/rj/58017/0116/0001/p000406-rj-m58017-z0116-s0001-aux.json'

        Args:
            ano (int): ano do pleito
            pleito (int): número do pleito
            regiao (str): código 2 caract de cada estado brasileiro ('br' é ilegal aqui)
            id_municipio (int): código TSE do município
            zona (int): número da zona eleitoral
            secao (int): número da seção eleitoral
        """
        
        base = rf'https://resultados.tse.jus.br/oficial'

        if ano is None:
            ano = self.section.contest.year
        if pleito is None:
            pleito = self.section.contest.contest_id
        if regiao is None:
            regiao = self.section.zone.city.state.abbr
        if id_municipio is None:
            id_municipio = self.section.zone.city.id
        if zona is None:
            zona = self.section.zone.id
        if secao is None:
            secao = self.section.id
        
        url_ano = f'ele{ano}'
        
        url_pleito_simples = str(pleito)
        url_pleito_p = f'p{url_pleito_simples:0>6s}'

        url_regiao = str(regiao).lower()

        url_mun_simples = f'{str(id_municipio):0>5s}'
        url_mun_m = f'm{url_mun_simples}'

        url_zona_simples = f'{str(zona):0>4s}'
        url_zona_z = f'z{url_zona_simples}'

        url_secao_simples = f'{str(secao):0>4s}'
        url_secao_s = f's{url_secao_simples}'

        url_final = rf'{base}/{url_ano}/arquivo-urna/{url_pleito_simples}/dados/{url_regiao}/'
        url_final += rf'{url_mun_simples}/{url_zona_simples}/{url_secao_simples}/'
        url_final += rf'{url_pleito_p}-{url_regiao}-{url_mun_m}-{url_zona_z}-{url_secao_s}-aux.json'
        
        return url_final

    def get_hash_dtrefresh(self, 
        hashdict: Dict, 
        dtfmt: Optional[str] = None
    ) -> list[str, dt]:

        if dtfmt is None:
            dtfmt = "%d/%m/%Y %H:%M:%S"
        
        try:
            hash_urna = hashdict['hash']
            dt_data_hash = hashdict['dr']
            dt_hora_hash = hashdict['hr']
            dt_hash = dt.strptime(dt_data_hash + ' ' + dt_hora_hash, dtfmt)
        except KeyError:
            raise ValueError('JSON em formato incorreto.')

        return hash_urna, dt_hash

    def get_url_download_urna(self, info: str, hash_urna: Optional[str] = None,  
        ano: Optional[int] = None, pleito: Optional[int] = None, 
        regiao: Optional[str] = None, 
        id_municipio: Optional[int] = None, zona: Optional[int] = None, secao: Optional[int] = None
    ) -> str:
        """gera URL para download de arquivos relacionados à apuração de cada urna individual, a saber: boletim de urna, registro digital de voto e log de urna.
        Ex. de URL: 'https://resultados.tse.jus.br/oficial/ele2022/arquivo-urna/406/dados/rj/60011/0004/0010/6a4b684a6243424a743479566268566c734a5650346e7259354a5a454b614f6f5834723542714f6a777a383d/o00406-6001100040010.bu'

        Args:
            ano (int): ano do pleito
            pleito (int): número do pleito
            regiao (str): código de 2 caract para os estados do brasil ('br' é ilegal aqui)
            id_municipio (int): código TSE do município
            zona (int): número da zona eleitoral
            secao (int): número da seção eleitoral
            hash (str): hash da urna
            info (str): qual informação se deseja baixar ('bu', 'imgbu', 'rdv', 'logjez')

        Returns:
            str: url para download
        """
        
        base = rf'https://resultados.tse.jus.br/oficial'
        
        if ano is None:
            ano = self.section.contest.year
        if pleito is None:
            pleito = self.section.contest.contest_id
        if regiao is None:
            regiao = self.section.zone.city.state.abbr
        if id_municipio is None:
            id_municipio = self.section.zone.city.id
        if zona is None:
            zona = self.section.zone.id
        if secao is None:
            secao = self.section.id
        if hash_urna is None:
            if self.hash_urna is None:
                url_info_urna = self.get_url_info_urna()
                jsondata = get_rl(url_info_urna).json()
                hash_urna, hash_dt = self.get_hash_dtrefresh(
                    hashdict = jsondata['hashes'][0]
                )
                
                self.hash_urna = hash_urna
                self.hash_dt = hash_dt
            else:
                hash_urna = self.hash_urna
        else:
            self.hash_urna = hash_urna

        url_ano = f'ele{ano}'
        
        url_pleito_simples = str(pleito)
        url_pleito_p = f'o{url_pleito_simples:0>5s}'

        url_regiao = str(regiao).lower()

        url_mun_simples = f'{str(id_municipio):0>5s}'
        url_mun_m = f'm{url_mun_simples}'

        url_zona_simples = f'{str(zona):0>4s}'
        url_zona_z = f'z{url_zona_simples}'

        url_secao_simples = f'{str(secao):0>4s}'
        url_secao_s = f's{url_secao_simples}'

        url_final = rf'{base}/{url_ano}/arquivo-urna/{url_pleito_simples}/dados/{url_regiao}/'
        url_final += rf'{url_mun_simples}/{url_zona_simples}/{url_secao_simples}/{hash_urna}/'
        url_final += rf'{url_pleito_p}-{url_mun_simples}{url_zona_simples}{url_secao_simples}.{info}'
        
        return url_final

    def get_info_download_path(self, caminho_dl_root: Optional[Path] = None):
        secao = self.section
        secao_url = f'{str(secao.id):0>4s}'

        zona = secao.zone
        zona_url = f'{str(zona.id):0>4s}'

        municipio = zona.city
        id_municipio_url = f'{str(municipio.id):0>5s}'

        ano = self.section.contest.year
        pleito_id = self.section.contest.contest_id
        
        if caminho_dl_root is None:
            caminho_dl_root = BU_ROOTDIR
            
        caminho_dl = caminho_dl_root.absolute().joinpath(
            Path(rf"{ano}/{pleito_id}/secoes_eleitorais/{id_municipio_url}/{zona_url}/{secao_url}")
        )

        return caminho_dl.resolve()

    def get_info_download_url(self, url_dl: Optional[str] = None):
        if url_dl is None:
            url_dl = self.get_url_download_urna(info = 'bu')
        
        return url_dl

    def download_bu(self, 
        url_dl: Optional[str] = None,
        caminho_dl_root: Optional[Path] = None,
    ):

        url_dl = self.get_info_download_url(url_dl = url_dl)

        # caminho download
        caminho_dl = self.get_info_download_path(caminho_dl_root)

        try:
            # os.makedirs(
            #     name = caminho_dl, 
            #     mode = 0o774,
            #     exist_ok = True
            # )
            caminho_dl.mkdir(mode = 0o774, parents = True, exist_ok = True)
        except FileExistsError:
            pass
        

        bu_path = caminho_dl.joinpath(Path(Path(url_dl).name))
        
        if bu_path.exists():
            bu_path.unlink()
        
        wget.download(
            url = url_dl, 
            out = str(caminho_dl)
        )

        return bu_path

    def processa_bu(self,
        bu_path: Optional[Path] = None, 
        asn1_paths: List = ASN1_PATHS
    ):
        if bu_path is None:
            if self.caminho_bu is None:
                raise ValueError('Caminho para arquivo do boletim da urna é indefinido!')
            bu_path = self.caminho_bu

        conv = asn1tools.compile_files(asn1_paths, codec="ber")
        with open(bu_path, "rb") as file:
            envelope_encoded = bytearray(file.read())
        envelope_decoded = conv.decode("EntidadeEnvelopeGenerico", envelope_encoded)
        bu_encoded = envelope_decoded["conteudo"]
        del envelope_decoded["conteudo"]  # remove o conteúdo para não imprimir como array de bytes
        bu_decoded = conv.decode("EntidadeBoletimUrna", bu_encoded)

        return envelope_decoded, bu_decoded

    def check_download_process_bu(self, bu_path_root: Optional[Path] = None):
        self.stale_data = self.check_data_staleness()
        if self.stale_data:
            self.caminho_bu = self.download_bu(caminho_dl_root = bu_path_root)
            self.envelope_urna, self.boletim_urna = self.processa_bu(self.caminho_bu)
        
        self.stale_data = False

    def votos_urna_df(self, bu: Optional[Dict] = None) -> pd.DataFrame:
        
        if bu is None:
            bu = self.boletim_urna

        votosdfs = []

        identificacao = bu
        resultados = bu['resultadosVotacaoPorEleicao']

        eleicao_stats_dfs = []

        # para cada eleicao (a eleicao para presidente tem numero diferente da dos outros)
        for resultado in resultados:
            id_eleicao = resultado['idEleicao']
            eleitores_aptos = resultado['qtdEleitoresAptos']

            resultados_votacao = resultado['resultadosVotacao']

            # para eleicoes com voto majoritário e proporcional
            for resultado_votacao in resultados_votacao:
                tipo_cargo = resultado_votacao['tipoCargo']
                eleitores_compareceram = resultado_votacao['qtdComparecimento']

                eleicao_stats_df = pd.DataFrame(
                    [ [ id_eleicao, tipo_cargo, eleitores_aptos, eleitores_compareceram ] ],
                    columns = ['id_eleicao', 'tipo_cargo', 'eleitores_aptos', 'comparecimento']
                )

                eleicao_stats_dfs.append(eleicao_stats_df)

                resultados_votacao_tipo = resultado_votacao['totaisVotosCargo']

                # para cada cargo
                for resultado_votacao_tipo in resultados_votacao_tipo:
                    cargo = resultado_votacao_tipo['codigoCargo'][1]

                    votos = resultado_votacao_tipo['votosVotaveis']

                    id_votos = [ voto['identificacaoVotavel'] if 'identificacaoVotavel' in voto else {'partido': pd.NA, 'codigo': pd.NA} for voto in votos ]

                    id_votos_df = pd.DataFrame(id_votos)
                    votosdf = pd.DataFrame(votos)
                    votosdf.drop(['assinatura', 'identificacaoVotavel'], inplace = True, axis = 'columns')
                    votosdf = pd.concat([votosdf, id_votos_df], axis = 'columns') 

                    # identificacao do voto
                    votosdf['cargo'] = cargo
                    votosdf['tipo_cargo'] = tipo_cargo
                    votosdf['e_valido'] = ~votosdf['tipoVoto'].isin(['branco', 'nulo'])
                    votosdf['id_eleicao'] = id_eleicao
                    
                    votosdfs.append(votosdf)
        
        # totalizacao das estatisticas
        stats_df = pd.concat(eleicao_stats_dfs)

        # totalizacao dos votos
        totalizacao = pd.concat(votosdfs)

        # dados de urna
        localizacao = identificacao['identificacaoSecao']

        stats_df['estado'] = self.section.zone.city.state.abbr
        stats_df['id_municipio'] = localizacao['municipioZona']['municipio']
        stats_df['zona'] = localizacao['municipioZona']['zona']
        stats_df['secao'] = localizacao['secao']

        totalizacao['id_municipio'] = localizacao['municipioZona']['municipio']
        totalizacao['zona'] = localizacao['municipioZona']['zona']
        totalizacao['secao'] = localizacao['secao']

        # dominio do cargo (pais, estado, municipio)
        # valores default
        totalizacao['dominio'] = 'municipio'
        totalizacao['dominio_local'] = totalizacao['id_municipio'].astype(str)
        # mascaras para filtragem
        mask_pais = totalizacao['cargo'] == 'presidente'
        mask_estado = totalizacao['cargo'].str.startswith('deputado') | (totalizacao['cargo'] == 'senador')
        # aplicacao da filtragem
        totalizacao.loc[mask_pais, 'dominio'] = 'pais'
        totalizacao.loc[mask_pais, 'dominio_local'] = 'br'
        totalizacao.loc[mask_estado, 'dominio'] = 'estado'
        totalizacao.loc[mask_estado, 'dominio_local'] = self.section.zone.city.state.abbr

        # tipagem
        totalizacao['tipoVoto'] = totalizacao['tipoVoto'].astype('category')
        totalizacao['partido'] = totalizacao['partido'].astype(pd.Int8Dtype())
        #totalizacao['codigo'] = pd.to_numeric(totalizacao['codigo']).astype(pd.Int16Dtype())
        totalizacao['cargo'] = totalizacao['cargo'].astype('category')
        totalizacao['tipo_cargo'] = totalizacao['tipo_cargo'].astype('category')
        # totalizacao['id_municipio'] = totalizacao['id_municipio'].astype(pd.Int16Dtype())
        # totalizacao['zona'] = totalizacao['zona'].astype(pd.Int16Dtype())
        # totalizacao['secao'] = totalizacao['secao'].astype(pd.Int16Dtype())
        totalizacao['dominio'] = totalizacao['dominio'].astype('category')
        
        # renomear colunas
        totalizacao.rename({
            'tipoVoto': 'tipo_voto',
            'quantidadeVotos': 'qtd_votos'
        }, axis = 'columns', inplace = True)

        return totalizacao.reset_index(drop = True), stats_df

    def __str__(self):
        if self.serial is not None:
            serial = f' #{str(self.serial)}'
        else:
            serial = ''
        
        secao = self.section
        zona = secao.zone
        municipio = zona.city

        ret = f'Urna{serial}, município {municipio.name}/{municipio.state.abbr} (cód. {str(municipio.id):0>5s})'
        ret += f', zona {str(zona.id):0>4s}'
        ret += f', seção {str(secao.id):0>4s}'

        return ret


def total_votes(candidates: List[Candidate]):
    counter = Counter(candidates)
    return counter

#%% 
# main
if __name__ == "__main__":
    rSE = Region(name = 'sudeste')
    sRJ = State(name = 'Rio de Janeiro', abbr = 'RJ', region = rSE)
    sRJ2 = State(name = 'Rio de Janeiro2', abbr = 'RJ', region = rSE)
    cNiteroi = City(id = 58653, name = 'Niterói', state = sRJ)
    # cand1 = Candidate(
    #     job = 'governador',
    #     number = 1,
    #     state = sRJ,
    #     city = cNiteroi
    # )
    # cand2 = Candidate(
    #     job = 'governador',
    #     number = 2,
    #     state = sRJ,
    #     city = cNiteroi
    # )