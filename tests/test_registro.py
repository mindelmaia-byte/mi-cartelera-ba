from cartelera.registro import cargar_cines


def test_registro_completo():
    cines = cargar_cines()
    por_tanda = {t: [c.nombre for c in cines if c.tanda == t] for t in (1, 2, 3, 4)}
    assert por_tanda[1] == ["Gaumont", "Cosmos", "Lorca", "MALBA", "Sala Lugones"]
    assert len(por_tanda[2]) == 15
    assert len(por_tanda[3]) == 13
    assert len(por_tanda[4]) == 8
    assert all(c.es_comercial for c in cines if c.tanda == 4)
    museo = next(c for c in cines if c.id == "museo-del-cine")
    assert museo.direccion == "Av. Agustín R. Caffarena 51, La Boca"
