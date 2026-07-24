import marketplace_inbox_bot as mib


def test_track_car_resolution_failure_incrementa_contador():
    failures = {}
    for expected_count in range(1, 5):
        count, should_alert = mib._track_car_resolution_failure(failures, "t1", threshold=5)
        assert count == expected_count
        assert should_alert is False


def test_track_car_resolution_failure_alerta_al_llegar_al_threshold():
    failures = {"t1": 4}
    count, should_alert = mib._track_car_resolution_failure(failures, "t1", threshold=5)
    assert count == 5
    assert should_alert is True


def test_track_car_resolution_failure_no_alerta_de_nuevo_tras_threshold():
    failures = {"t1": 5}
    count, should_alert = mib._track_car_resolution_failure(failures, "t1", threshold=5)
    assert count == 6
    assert should_alert is False


def test_track_car_resolution_failure_threads_distintos_no_se_mezclan():
    failures = {}
    mib._track_car_resolution_failure(failures, "t1", threshold=5)
    mib._track_car_resolution_failure(failures, "t1", threshold=5)
    count, _ = mib._track_car_resolution_failure(failures, "t2", threshold=5)
    assert count == 1
    assert failures == {"t1": 2, "t2": 1}


def test_session_alert_transition_primera_caida_alerta():
    should_alert, new_state = mib._session_alert_transition(currently_logged_in=False, alert_already_sent=False)
    assert should_alert is True
    assert new_state is True


def test_session_alert_transition_no_repite_alerta_mientras_sigue_caida():
    should_alert, new_state = mib._session_alert_transition(currently_logged_in=False, alert_already_sent=True)
    assert should_alert is False
    assert new_state is True


def test_session_alert_transition_reset_al_recuperar_sesion():
    should_alert, new_state = mib._session_alert_transition(currently_logged_in=True, alert_already_sent=True)
    assert should_alert is False
    assert new_state is False


def test_session_alert_transition_sin_cambios_si_ya_estaba_bien():
    should_alert, new_state = mib._session_alert_transition(currently_logged_in=True, alert_already_sent=False)
    assert should_alert is False
    assert new_state is False
