from app.tools import persistence


def test_document_library_filters_search_and_decision_export(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "_DB_PATH", tmp_path / "aid_test.db")
    persistence.init_db()

    team_id = persistence.ensure_default_team("alice", "admin")
    project_id = persistence.create_project(team_id, "Werk 1", "alice")

    doc_id = persistence.save_library_document(
        team_id=team_id,
        project_id=project_id,
        uploaded_by="alice",
        title="Stellplatzsatzung Musterstadt",
        filename="stellplatzsatzung.md",
        mime_type="text/markdown",
        text="Stellplatzsatzung: 1 Stellplatz je 100 m2 Produktion. GRZ 0,8. GFZ 2,4.",
        scope="project",
        planning_blocks=["master", "layout"],
        rights_notice=True,
    )
    assert doc_id > 0

    master_docs = persistence.list_library_documents(team_id, project_id, "master")
    process_docs = persistence.list_library_documents(team_id, project_id, "process")
    assert len(master_docs) == 1
    assert process_docs == []

    full_doc = persistence.get_library_document(doc_id, team_id=team_id)
    assert full_doc["text"].startswith("Stellplatzsatzung")
    assert persistence.update_library_document_blocks(doc_id, team_id=team_id, planning_blocks=["process"]) is True
    assert persistence.list_library_documents(team_id, project_id, "master") == []
    assert len(persistence.list_library_documents(team_id, project_id, "process")) == 1
    assert persistence.update_library_document_blocks(doc_id, team_id=team_id, planning_blocks=["master", "layout"]) is True

    hits = persistence.search_library_chunks(
        team_id=team_id,
        project_id=project_id,
        planning_block="master",
        query="Stellplatz GRZ",
        limit=3,
    )
    assert hits
    assert hits[0]["source_ref"].startswith("Quelle: Stellplatzsatzung")

    persistence.save_decision_log(
        team_id=team_id,
        project_id=project_id,
        user="alice",
        planning_block="master",
        phase="1.2",
        decision="GRZ uebernommen",
        method="RAG + Pruefung",
        rationale="Wert aus Satzung extrahiert.",
        inputs={"grz": 0.8},
        sources=[hits[0]],
    )
    md = persistence.export_decision_log_markdown(team_id, project_id)
    assert "# Entscheidungsprotokoll" in md
    assert "GRZ uebernommen" in md
    assert "Quelle: Stellplatzsatzung" in md

    assert persistence.delete_library_document(doc_id, team_id=team_id, user="alice") is True
    assert persistence.list_library_documents(team_id, project_id, "master") == []
