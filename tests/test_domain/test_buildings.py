from app.domain.buildings import MATCH_RADIUS_M, Building, BuildingIndex

# Um grau de longitude em Belo Horizonte vale ~104,6 km; 0,0001° ≈ 10,5 m.
BASE_LAT, BASE_LON = -19.9333, -43.9333


def _predio(numero, dlat=0.0, dlon=0.0, rua="rua_dos_aimores", tipo="AP", **extra):
    return Building(
        street_key=rua,
        number_key=numero,
        lat=BASE_LAT + dlat,
        lon=BASE_LON + dlon,
        construction_type=tipo,
        **extra,
    )


def test_resolve_o_predio_em_cima_da_coordenada():
    indice = BuildingIndex.build([_predio("1862")])
    assert indice.resolve("rua_dos_aimores", BASE_LAT, BASE_LON) == "1862"


def test_escolhe_o_lote_mais_proximo_entre_vizinhos():
    indice = BuildingIndex.build(
        [_predio("100"), _predio("200", dlon=0.0002), _predio("300", dlon=0.0004)]
    )
    assert indice.resolve("rua_dos_aimores", BASE_LAT, BASE_LON + 0.00022) == "200"


def test_nao_resolve_fora_do_raio():
    # ~105 m de distância, bem além dos 50 m.
    indice = BuildingIndex.build([_predio("100", dlon=0.001)])
    assert indice.resolve("rua_dos_aimores", BASE_LAT, BASE_LON) is None


def test_nao_atravessa_para_a_rua_de_tras():
    # O prédio da outra rua está colado, mas a rua do anúncio manda.
    indice = BuildingIndex.build([_predio("100", rua="rua_de_tras")])
    assert indice.resolve("rua_dos_aimores", BASE_LAT, BASE_LON) is None
    assert indice.resolve("rua_de_tras", BASE_LAT, BASE_LON) == "100"


def test_encontra_lote_na_celula_vizinha_da_grade():
    # A grade tem célula de ~55 m; um vizinho a 30 m pode cair na célula ao
    # lado, e a busca tem de olhar as oito adjacentes.
    for deslocamento in (0.0003, -0.0003):
        indice = BuildingIndex.build([_predio("100", dlon=deslocamento)])
        assert indice.resolve("rua_dos_aimores", BASE_LAT, BASE_LON) == "100"


def test_sem_rua_ou_sem_coordenada_nao_resolve():
    indice = BuildingIndex.build([_predio("100")])
    assert indice.resolve(None, BASE_LAT, BASE_LON) is None
    assert indice.resolve("rua_dos_aimores", None, BASE_LON) is None
    assert indice.resolve("rua_dos_aimores", BASE_LAT, None) is None


def test_indice_vazio_nao_resolve_nada():
    assert BuildingIndex.build([]).resolve("rua_dos_aimores", BASE_LAT, BASE_LON) is None


def test_raio_configuravel_afrouxa_a_busca():
    indice = BuildingIndex.build([_predio("100", dlon=0.0007)])  # ~73 m
    assert indice.resolve("rua_dos_aimores", BASE_LAT, BASE_LON) is None
    assert indice.resolve("rua_dos_aimores", BASE_LAT, BASE_LON, radius_m=100) == "100"


def test_o_raio_padrao_e_o_medido_em_cinquenta_metros():
    assert MATCH_RADIUS_M == 50.0


def test_lookup_devolve_o_endereco_do_cadastro_pelo_numero():
    indice = BuildingIndex.build([_predio("1862", finish_standard="P4", units_count=40)])
    achado = indice.lookup("AP", "rua_dos_aimores", "1862")
    assert achado is not None
    assert achado.finish_standard == "P4"
    assert achado.units_count == 40
    assert indice.lookup("AP", "rua_dos_aimores", "9999") is None
    assert indice.lookup("CA", "rua_dos_aimores", "1862") is None


def test_lookup_sem_argumento_completo_e_none():
    indice = BuildingIndex.build([_predio("1862")])
    assert indice.lookup(None, "rua_dos_aimores", "1862") is None
    assert indice.lookup("AP", None, "1862") is None
    assert indice.lookup("AP", "rua_dos_aimores", None) is None


def test_lote_sem_coordenada_ainda_entra_no_lookup_por_numero():
    sem_ponto = Building(
        street_key="rua_dos_aimores",
        number_key="50",
        lat=None,
        lon=None,
        construction_type="AP",
        finish_standard="P2",
    )
    indice = BuildingIndex.build([sem_ponto])
    assert indice.lookup("AP", "rua_dos_aimores", "50").finish_standard == "P2"
    assert indice.resolve("rua_dos_aimores", BASE_LAT, BASE_LON) is None


# --- limites da cidade --------------------------------------------------------


def test_o_retangulo_sai_dos_proprios_pontos_com_folga():
    from app.domain.buildings import CITY_BOUNDS_MARGIN, city_bounds

    limites = city_bounds([(-19.9, -43.9), (-20.0, -44.0)])
    assert limites == (
        -20.0 - CITY_BOUNDS_MARGIN,
        -19.9 + CITY_BOUNDS_MARGIN,
        -44.0 - CITY_BOUNDS_MARGIN,
        -43.9 + CITY_BOUNDS_MARGIN,
    )


def test_sem_ponto_nao_ha_retangulo():
    from app.domain.buildings import city_bounds

    assert city_bounds([]) is None
    assert city_bounds([(None, None)]) is None


def test_o_ponto_da_cidade_passa_e_o_de_outro_estado_nao():
    from app.domain.buildings import city_bounds, within_bounds

    bh = city_bounds([(-20.05, -44.06), (-19.77, -43.86)])
    assert within_bounds(-19.92, -43.94, bh)
    # Centro geográfico do Brasil: o que a Loft publica quando não sabe.
    assert not within_bounds(-13.901082, -50.713422, bh)
    # Florianópolis e Rio, devolvidos para endereços de Belo Horizonte.
    assert not within_bounds(-27.599621, -48.609340, bh)
    assert not within_bounds(-22.906847, -43.172897, bh)
    # Par arredondado, outro sintoma de coordenada inventada.
    assert not within_bounds(-19.0, -43.0, bh)


def test_a_folga_deixa_passar_quem_esta_na_divisa():
    from app.domain.buildings import city_bounds, within_bounds

    bh = city_bounds([(-20.05, -44.06), (-19.77, -43.86)])
    assert within_bounds(-19.76, -43.85, bh)


def test_sem_retangulo_conhecido_a_coordenada_passa():
    from app.domain.buildings import within_bounds

    # Cidade sem cadastro carregado: descartar seria inventar um critério.
    assert within_bounds(-19.92, -43.94, None)


def test_coordenada_ausente_nunca_passa():
    from app.domain.buildings import within_bounds

    assert not within_bounds(None, -43.9, None)
    assert not within_bounds(-19.9, None, None)
