#!/usr/bin/env python3
#-*- coding: utf-8 -*-

from datetime import datetime as dt
import pytest
from contextlib import contextmanager
from .. import votecounter as vc

from urllib.error import URLError
from asn1tools.codecs.ber import DecodeTagError

import warnings
warnings.filterwarnings('ignore')

BU_ROOTDIR_TEST = vc.Path(rf'temp_test_data/').resolve()

# from https://stackoverflow.com/questions/50186904/pathlib-recursively-remove-directory
def rmtree(f: vc.Path):
    if f.is_file():
        f.unlink()
    else:
        for child in f.iterdir():
            rmtree(child)
        f.rmdir()

@contextmanager
def does_not_raise():
    yield

@pytest.fixture(scope = 'session')
def get_regions():
    brasil = vc.Country(name = 'Brasil')
    regions = {
        'SE': vc.Region(name = 'Sudeste', abbr = 'SE', country = brasil),
        'NE': vc.Region(name = 'Nordeste', abbr = 'NE', country = brasil),
        'S': vc.Region(name = 'Sul', abbr = 'S', country = brasil),
        'N': vc.Region(name = 'Norte', abbr = 'N', country = brasil),
        'CO': vc.Region(name = 'Centro-Oeste', abbr = 'CO', country = brasil),
    }

    return regions

@pytest.fixture(scope = 'session')
def get_states(get_regions):

    states_dict = {
        'AC': ('Acre', 'N'),
        'AL': ('Alagoas', 'NE'),
        'AP': ('Amapá', 'N'),
        'AM': ('Amazonas', 'N'),
        'BA': ('Bahia', 'NE'),
        'CE': ('Ceará', 'NE'),
        'DF': ('Distrito Federal', 'CO'),
        'ES': ('Espírito Santo', 'SE'),
        'GO': ('Goiás', 'CO'),
        'MA': ('Maranhão', 'NE'),
        'MT': ('Mato Grosso', 'CO'),
        'MS': ('Mato Grosso do Sul', 'CO'),
        'MG': ('Minas Gerais', 'SE'),
        'PA': ('Pará', 'N'),
        'PB': ('Paraíba', 'NE'),
        'PR': ('Paraná', 'S'),
        'PE': ('Pernambuco', 'NE'),
        'PI': ('Piauí', 'NE'),
        'RJ': ('Rio de Janeiro', 'SE'),
        'RN': ('Rio Grande do Norte', 'NE'),
        'RS': ('Rio Grande do Sul', 'S'),
        'RO': ('Rondônia', 'N'),
        'RR': ('Roraima', 'N'),
        'SC': ('Santa Catarina', 'S'),
        'SP': ('São Paulo', 'SE'),
        'SE': ('Sergipe', 'NE'),
        'TO': ('Tocantins', 'N'),
    }

    states = { 
        abbr: vc.State(
            name = name_reg[0], 
            abbr = abbr, 
            region = get_regions[name_reg[1]]
        ) for abbr, name_reg in states_dict.items() 
    }

    states.update({
        'ZZ': vc.State(
            name = 'Exterior',
            abbr = 'ZZ',
            region = None
        )
    })

    return states

@pytest.fixture(scope = 'session')
def get_election():
    # pleito de 2022, eleições gerais ordinárias
    pleito_2022_1 = vc.Contest(year = 2022, contest_id = 406) 
    
    # eleição para cargos sem ser presidente, 2022 primeiro turno
    eleicao_resto_2022_1 = vc.Election(id = 546, contest = pleito_2022_1)

    return eleicao_resto_2022_1

@pytest.fixture(scope = 'session')
def get_city_zone_section(get_states, get_election):
    estado_abbr = 'RJ'
    state = get_states[estado_abbr]
    contest = get_election.contest
    
    # pegar info de secoes eleitorais
    url = state.get_url_info_mun_zona_secao(
        ano = contest.year,
        pleito = contest.contest_id
    )
    restapi = vc.get_rl(url)
    jsondata = restapi.json()
    
    municipio = jsondata['abr'][0]['mu'][0]
    id_municipio = int(municipio['cd'])
    municipio_obj = vc.City(
        id = id_municipio,
        name = municipio['nm'],
        state = get_states[estado_abbr]
    )

    zona = municipio['zon'][0]
    id_zona = zona['cd']
    zona_obj = vc.ElectionZone(
            id = id_zona,
            city = municipio_obj
        )

    secao = zona['sec'][0]
    id_secao = int(secao['ns'])
    secao_obj = vc.ElectionSection(
        id = id_secao,
        zone = zona_obj,
        contest = contest
    )

    return municipio_obj, zona_obj, secao_obj

@pytest.fixture(scope = 'function')
def get_urna(get_city_zone_section):
    _, _, secao_obj = get_city_zone_section
    urna_obj = vc.VotingMachine(section = secao_obj)

    return urna_obj

@pytest.fixture(scope = 'function')
def get_urnas():
    return


@pytest.fixture
def remove_vm_files(get_urna):
    yield
    rmtree(BU_ROOTDIR_TEST)


class TestState:
    def test_states_url_resultados_parciais(self, get_regions, get_states, get_election):
        states = get_states
        election = get_election

        estado_invalido = vc.State(
            name = 'Riacho de Fevereiro',
            abbr = 'RF',
            region = None
        )

        estado_brasil = vc.State(
            name = 'Brasil',
            abbr = 'BR',
            region = None
        )

        cargos = {}
        cargos_possiveis = [ 'erro', 'presidente', 'governador', 'senador' , 'deputado federal', 'deputado estadual']
        
        for cargo in cargos_possiveis[2:]:
            cargos[cargo] = {}
            for abbr, estado_obj in states.items():
                
                url = estado_obj.get_url_votos(
                    ano = election.contest.year,
                    eleicao = election.id,
                    cargo = cargo
                )
                restapi = vc.get_rl(url)

                # pessoas no exterior não votam para cargos exceto o de presidente
                if abbr == 'ZZ':
                    assert not (200 <= restapi.status_code < 300)
                
                # distrito federal elege deputados distritais, não estaduais
                elif abbr == 'DF' and cargo == 'deputado estadual': 
                    assert not (200 <= restapi.status_code < 300)

                else:
                    assert 200 <= restapi.status_code < 300

            # resumo do brasil
            cargos[cargo]['BR'] = estado_brasil.get_url_votos(
                ano = election.contest.year,
                eleicao = election.id,
                cargo = cargo
            )
            restapi = vc.get_rl(cargos[cargo]['BR'])

            # o resumo de votos no brasil só está disponível para eleições para presidente.
            assert not (200 <= restapi.status_code < 300)
        
        # estado ilegal
        for cargo in cargos_possiveis[2:]:
            url = estado_invalido.get_url_votos(
                ano = election.contest.year,
                eleicao = election.id,
                cargo = cargo
            )
            restapi = vc.get_rl(url)
            assert not (200 <= restapi.status_code < 300)

        # cargos ilegais: 'erro' (KeyError: não vai encontrar no dicionário que relaciona cargo e código) 
        #                 'presidente' (há um código de eleição (544) só para presidente 2022.1)
        with pytest.raises(KeyError) as excinfo:
            for cargo in cargos_possiveis[:2]:
                url = estado_brasil.get_url_votos(
                    ano = election.contest.year,
                    eleicao = election.id,
                    cargo = cargo
                )
                restapi = vc.get_rl(url)
                assert not (200 <= restapi.status_code < 300)
            
    def test_states_url_info_mun_zona_sec(self, get_states, get_election):
        states = get_states
        election = get_election
        contest = election.contest

        estado_invalido = vc.State(
            name = 'Riacho de Fevereiro',
            abbr = 'RF',
            region = None
        )

        estado_brasil = vc.State(
            name = 'Brasil',
            abbr = 'BR',
            region = None
        )

        urls = {}
        
        # não deve dar nenhum problema
        for abbr, estado_obj in states.items():
            url = estado_obj.get_url_info_mun_zona_secao(
                ano = contest.year,
                pleito = contest.contest_id
            )
            urls[abbr] = url
            restapi = vc.get_rl(url)
            assert 200 <= restapi.status_code < 300
        
        # estado inválido
        url = estado_invalido.get_url_info_mun_zona_secao(
            ano = contest.year,
            pleito = contest.contest_id,
        )
        restapi = vc.get_rl(url)
        assert not (200 <= restapi.status_code < 300)

        # brasil não tem informações sobre municipios, é necessário pegar pelos estados individuais
        url = estado_brasil.get_url_info_mun_zona_secao(
            ano = contest.year,
            pleito = contest.contest_id,
        )
        restapi = vc.get_rl(url)
        assert not (200 <= restapi.status_code < 300)
    
    def test_process_info_mun_zona_secao(self, get_states, get_election):
        state = get_states['RJ']
        contest = get_election.contest

        assert vc.VotingMachine.all_vms == []

        municipios, zonas, secoes = state.process_info_mun_zona_secao(
            ano = contest.year,
            pleito = contest.contest_id,
        )

        assert isinstance(secoes, dict)
        assert len(vc.VotingMachine.all_vms) == len(secoes.keys())


class TestVotingMachine:

    def test_url_info_urna(self, get_urna):
        urna = get_urna

        # não são esperados erros. HTTP response 200
        url = urna.get_url_info_urna()
        restapi = vc.get_rl(url)
        assert 200 <= restapi.status_code < 300

    def test_url_download_urna_hash_invalida(self, get_urna):
        urna = get_urna
        
        # hash inválida
        url = urna.get_url_download_urna(info = 'bu', hash_urna = '123')
        restapi = vc.get_rl(url)
        assert not (200 <= restapi.status_code < 300)
    
    def test_url_download_urna_hash_api(self, get_urna):
        urna = get_urna
        
        # hash inicialmente vazia
        assert urna.hash_urna is None
        assert urna.hash_dt.year != urna.section.contest.year

        # hash lida da api
        url = urna.get_url_download_urna(info = 'bu')
        restapi = vc.get_rl(url)
        assert 200 <= restapi.status_code < 300

        # hash preenchida na instancia de urna
        assert urna.hash_urna is not None
        assert urna.hash_dt.year == urna.section.contest.year
    
    def test_get_hashdt_refresh_dict_valido(self, get_urna):
        urna = get_urna

        url = urna.get_url_info_urna()
        restapi = vc.get_rl(url)
        jsondata = restapi.json()

        hash_dict = jsondata['hashes'][0]

        with does_not_raise():
            hash_urna, hash_dt = urna.get_hash_dtrefresh(hashdict = hash_dict)
            assert isinstance(hash_urna, str)
            assert isinstance(hash_dt, dt)
    
    def test_get_hashdt_refresh_dict_invalido(self, get_urna):
        urna = get_urna

        hash_dict = {}
        with pytest.raises(ValueError) as excinfo:
            hash_urna, hash_dt = urna.get_hash_dtrefresh(hashdict = hash_dict)
    
    def test_download_bu(self, get_urna, remove_vm_files):
        urna = get_urna

        arq = urna.download_bu(caminho_dl_root = BU_ROOTDIR_TEST)

        assert arq.exists()

    def test_download_bu_url_invalida(self, get_urna):
        urna = get_urna
        
        # o método download_bu usa o wget para download: deve portanto levantar o URLError se a url for inválida
        with pytest.raises(URLError) as excinfo:
            arq = urna.download_bu(caminho_dl_root = BU_ROOTDIR_TEST, url_dl = 'https://invalid.example')
        
        # variável não deveria existir
        with pytest.raises(UnboundLocalError) as excinfo:
            assert arq is None
    
    def test_processa_bu_valido(self, get_urna, remove_vm_files):
        urna = get_urna

        caminho_bu = urna.download_bu(caminho_dl_root = BU_ROOTDIR_TEST)

        with does_not_raise():
            envelope, bu = urna.processa_bu(caminho_bu)

            # se a função processa_bu funcionou como deveria, a variável 'bu' contem um dicionário com um layout específico
            # vamos checar uma chave qualquer desse dicionário
            assert isinstance(bu['urna'], dict)
    
    def test_processa_bu_invalido(self, get_urna):
        urna = get_urna

        caminho_bu = vc.Path(r'README.md')

        with pytest.raises(DecodeTagError):
            envelope, bu = urna.processa_bu(caminho_bu)

    def test_check_download_process_bu(self, get_urna, remove_vm_files):
        urna = get_urna

        assert urna.stale_data is True
        assert urna.caminho_bu is None
        assert urna.envelope_urna is None
        assert urna.boletim_urna is None
            
        urna.check_download_process_bu(bu_path_root = BU_ROOTDIR_TEST)
        
        assert urna.stale_data is False
        assert isinstance(urna.caminho_bu, vc.Path)
        assert isinstance(urna.envelope_urna, dict)
        assert isinstance(urna.boletim_urna, dict)
    
    def test_download_multiple(self, get_urnas):
        pass

    def test_df_votes(self):
        pass

class TestPartyFederation:

    def test_party(self):
        fPSOLREDE = vc.PartyFederation(name = 'PSOL REDE')
        pPSOL = vc.Party(number = 50, name = 'PSOL', federation = fPSOLREDE)
        pPL = vc.Party(number = 22, name = 'PL')
        pPLfake = vc.Party(number = 22, name = 'PL2')

        assert pPSOL.name == 'PSOL' and pPSOL.number == 50
        assert pPL == pPLfake
        assert not pPL == pPSOL