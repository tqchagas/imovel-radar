import math

import pytest

from app.domain.geo import (
    BH_UTM_ZONE,
    haversine_m,
    polygon_centroid,
    utm_central_meridian,
    utm_to_latlon,
)


def test_meridiano_central_do_fuso_23_e_menos_45():
    assert utm_central_meridian(BH_UTM_ZONE) == -45


def test_no_meridiano_central_a_longitude_e_exatamente_a_do_fuso():
    # Propriedade da projeção, não medição: easting 500.000 é o meridiano
    # central por definição. Serve de âncora sem depender de um ponto que eu
    # teria de acreditar de fora.
    _, lon = utm_to_latlon(500000, 7796500)
    assert lon == pytest.approx(-45.0, abs=1e-9)


def test_o_equador_esta_no_falso_northing_do_hemisferio_sul():
    lat, _ = utm_to_latlon(500000, 10000000)
    assert lat == pytest.approx(0.0, abs=1e-9)


def test_um_lote_do_cadastro_cai_dentro_de_belo_horizonte():
    # Geometria real do cadastro da PBH, regional Hipercentro.
    lat, lon = utm_to_latlon(610785.44, 7796257.0)
    assert -20.10 < lat < -19.70
    assert -44.10 < lon < -43.80


def test_converte_dentro_do_metro_no_ida_e_volta():
    # Sem a projeção direta para comparar, o teste ancora em dois pontos
    # separados por um deslocamento UTM conhecido: 100 m em northing têm de
    # virar ~100 m de distância geográfica.
    a = utm_to_latlon(611000, 7796000)
    b = utm_to_latlon(611000, 7796100)
    assert haversine_m(*a, *b) == pytest.approx(100, abs=1.0)


def test_centroide_ignora_o_vertice_que_fecha_o_anel():
    quadrado = "POLYGON ((0 0,10 0,10 10,0 10,0 0))"
    assert polygon_centroid(quadrado) == (5.0, 5.0)


def test_centroide_de_geometria_vazia_ou_ausente_e_none():
    assert polygon_centroid(None) is None
    assert polygon_centroid("") is None
    assert polygon_centroid("POLYGON EMPTY") is None


def test_centroide_aceita_coordenada_negativa_e_decimal():
    centro = polygon_centroid("POLYGON ((-1.5 2.5,-0.5 2.5,-0.5 3.5,-1.5 3.5,-1.5 2.5))")
    assert centro == (pytest.approx(-1.0), pytest.approx(3.0))


def test_haversine_zero_para_o_mesmo_ponto():
    assert haversine_m(-19.9, -43.9, -19.9, -43.9) == 0


def test_haversine_simetrica():
    ida = haversine_m(-19.9, -43.9, -19.91, -43.92)
    volta = haversine_m(-19.91, -43.92, -19.9, -43.9)
    assert ida == pytest.approx(volta)


def test_um_grau_de_latitude_tem_cerca_de_111_km():
    assert haversine_m(-19.0, -43.9, -20.0, -43.9) == pytest.approx(111195, rel=0.01)


def test_centroide_de_multipolygon_media_todos_os_aneis():
    # O cadastro traz lote com mais de um anel; a média não pode explodir.
    centro = polygon_centroid("MULTIPOLYGON (((0 0,2 0,2 2,0 2,0 0)),((4 4,6 4,6 6,4 6,4 4)))")
    assert centro is not None
    x, y = centro
    assert 0 < x < 6 and 0 < y < 6
    assert not math.isnan(x)
