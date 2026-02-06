"""
Roteiro de testes do Shadow MVP.
Uso: python test_shadow.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage import Storage
from tools import setup_default_tools, ToolContext
from contact_resolver import ContactResolver
from message_handler import handle_message

# Cores para output (funciona no Windows 10+)
os.system("")  # Habilita ANSI no Windows
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def test_result(name: str, passed: bool, details: str = ""):
    """Exibe resultado de um teste."""
    status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    print(f"  [{status}] {name}")
    if details and not passed:
        print(f"         {YELLOW}{details}{RESET}")


def run_tests():
    """Executa todos os testes."""
    print("=" * 60)
    print("        ROTEIRO DE TESTES DO SHADOW MVP")
    print("=" * 60)

    storage = Storage()
    owner = os.getenv("SHADOW_OWNER_E164", "+5511999999999")
    registry = setup_default_tools()
    context = ToolContext(user_phone=owner, storage=storage)

    passed = 0
    failed = 0

    # ========== TESTE 1: Storage ==========
    print("\n[STORAGE]")

    # 1.1 Criar tarefa
    try:
        task = storage.create_task("Tarefa de teste automatizado", None)
        ok = task.id is not None
        test_result("Criar tarefa", ok)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Criar tarefa", False, str(e))
        failed += 1

    # 1.2 Listar tarefas
    try:
        tasks = storage.list_tasks(5)
        ok = len(tasks) > 0
        test_result("Listar tarefas", ok, f"Encontradas: {len(tasks)}")
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Listar tarefas", False, str(e))
        failed += 1

    # 1.3 Criar compromisso
    try:
        appt = storage.create_appointment("Compromisso teste", "2025-02-10T10:00:00")
        ok = appt.id is not None
        test_result("Criar compromisso", ok)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Criar compromisso", False, str(e))
        failed += 1

    # 1.4 Upsert contato
    try:
        storage.upsert_contact("+5511999998888", "Teste Automatizado")
        ok = True
        test_result("Upsert contato", ok)
        passed += 1
    except Exception as e:
        test_result("Upsert contato", False, str(e))
        failed += 1

    # ========== TESTE 2: Contact Resolver ==========
    print("\n[CONTACT RESOLVER]")

    resolver = ContactResolver(storage)

    # 2.1 Resolver alias
    try:
        resolved = resolver.resolve(owner, "joao")
        ok = resolved.phone is not None
        test_result("Resolver alias 'joao'", ok, f"Phone: {resolved.phone}" if ok else "Nao encontrado")
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Resolver alias 'joao'", False, str(e))
        failed += 1

    # 2.2 Resolver nome exato
    try:
        resolved = resolver.resolve(owner, "Maria Santos")
        ok = resolved.phone is not None
        test_result("Resolver nome 'Maria Santos'", ok)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Resolver nome 'Maria Santos'", False, str(e))
        failed += 1

    # 2.3 Resolver telefone direto
    try:
        resolved = resolver.resolve(owner, "+5511988887777")
        ok = resolved.phone == "+5511988887777"
        test_result("Resolver telefone direto", ok)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Resolver telefone direto", False, str(e))
        failed += 1

    # 2.4 Extrair mencoes
    try:
        mentions = resolver.extract_mentions("Preciso falar com João sobre o projeto da Maria")
        ok = len(mentions) > 0
        test_result("Extrair mencoes do texto", ok, f"Mencoes: {mentions}")
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Extrair mencoes do texto", False, str(e))
        failed += 1

    # ========== TESTE 3: Tools ==========
    print("\n[TOOLS]")

    # 3.1 list_contacts
    try:
        result = registry.execute("list_contacts", {"limit": 5}, context)
        ok = result.success
        test_result("Tool: list_contacts", ok, result.message)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Tool: list_contacts", False, str(e))
        failed += 1

    # 3.2 get_contact
    try:
        result = registry.execute("get_contact", {"identifier": "joao"}, context)
        ok = result.success
        test_result("Tool: get_contact", ok, result.message)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Tool: get_contact", False, str(e))
        failed += 1

    # 3.3 create_task
    try:
        result = registry.execute("create_task", {"title": "Nova tarefa via tool"}, context)
        ok = result.success
        test_result("Tool: create_task", ok, result.message)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Tool: create_task", False, str(e))
        failed += 1

    # 3.4 list_tasks
    try:
        result = registry.execute("list_tasks", {"limit": 5}, context)
        ok = result.success
        test_result("Tool: list_tasks", ok, result.message)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Tool: list_tasks", False, str(e))
        failed += 1

    # 3.5 get_contact_tasks
    try:
        result = registry.execute("get_contact_tasks", {"contact": "joao"}, context)
        ok = result.success
        test_result("Tool: get_contact_tasks", ok, result.message)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Tool: get_contact_tasks", False, str(e))
        failed += 1

    # 3.6 search_contact_history
    try:
        result = registry.execute("search_contact_history", {"contact": "joao", "limit": 5}, context)
        ok = result.success
        test_result("Tool: search_contact_history", ok, result.message)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Tool: search_contact_history", False, str(e))
        failed += 1

    # ========== TESTE 4: Message Handler ==========
    print("\n[MESSAGE HANDLER]")

    # 4.1 Comando ping
    try:
        result = handle_message(
            {
                "body": "ping",
                "sender_e164": owner,
                "owner_e164": owner,
                "is_owner": True,
            },
            storage,
        )
        ok = "online" in result.get("reply", "").lower()
        test_result("Comando: ping", ok)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Comando: ping", False, str(e))
        failed += 1

    # 4.2 Comando ajuda
    try:
        result = handle_message(
            {
                "body": "ajuda",
                "sender_e164": owner,
                "owner_e164": owner,
                "is_owner": True,
            },
            storage,
        )
        ok = result.get("reply") is not None and len(result.get("reply", "")) > 50
        test_result("Comando: ajuda", ok)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Comando: ajuda", False, str(e))
        failed += 1

    # 4.3 Listar tarefas
    try:
        result = handle_message(
            {
                "body": "mostrar tarefas",
                "sender_e164": owner,
                "owner_e164": owner,
                "is_owner": True,
            },
            storage,
        )
        ok = result.get("reply") is not None
        test_result("Comando: mostrar tarefas", ok)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Comando: mostrar tarefas", False, str(e))
        failed += 1

    # 4.4 Criar tarefa via texto
    try:
        result = handle_message(
            {
                "body": "tarefa: testar sistema automatizado",
                "sender_e164": owner,
                "owner_e164": owner,
                "is_owner": True,
            },
            storage,
        )
        ok = "criada" in result.get("reply", "").lower()
        test_result("Criar tarefa via texto", ok)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Criar tarefa via texto", False, str(e))
        failed += 1

    # 4.5 Processar mensagem de contato (nao owner)
    try:
        result = handle_message(
            {
                "body": "Preciso do relatório para amanha",
                "sender_e164": "+5511988887777",
                "sender_name": "João Silva",
                "owner_e164": owner,
                "is_owner": False,
                "chat_id": "+5511988887777@s.whatsapp.net",
            },
            storage,
        )
        ok = result.get("intent") == "ingest"
        test_result("Processar mensagem de contato", ok, f"Intent: {result.get('intent')}")
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Processar mensagem de contato", False, str(e))
        failed += 1

    # 4.6 Resumo do dia
    try:
        result = handle_message(
            {
                "body": "resumo do dia",
                "sender_e164": owner,
                "owner_e164": owner,
                "is_owner": True,
            },
            storage,
        )
        ok = result.get("reply") is not None and "resumo" in result.get("reply", "").lower()
        test_result("Comando: resumo do dia", ok)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Comando: resumo do dia", False, str(e))
        failed += 1

    # ========== TESTE 5: Memory ==========
    print("\n[MEMORY]")

    # 5.1 Salvar memoria
    try:
        mid = storage.save_contact_memory(
            owner_id=owner,
            text="Teste de memoria do sistema automatizado",
            category="fact",
            importance=0.5,
        )
        ok = mid is not None
        test_result("Salvar memoria", ok)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Salvar memoria", False, str(e))
        failed += 1

    # 5.2 Listar memorias
    try:
        memories = storage.list_contact_memories(owner, limit=5)
        ok = len(memories) > 0
        test_result("Listar memorias", ok, f"Encontradas: {len(memories)}")
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Listar memorias", False, str(e))
        failed += 1

    # ========== TESTE 6: Aliases ==========
    print("\n[ALIASES]")

    # 6.1 Adicionar alias
    try:
        ok = storage.add_contact_alias(owner, "+5511999998888", "teste_auto")
        test_result("Adicionar alias", ok)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Adicionar alias", False, str(e))
        failed += 1

    # 6.2 Resolver alias criado
    try:
        phone = storage.resolve_alias(owner, "teste_auto")
        ok = phone == "+5511999998888"
        test_result("Resolver alias criado", ok)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Resolver alias criado", False, str(e))
        failed += 1

    # 6.3 Listar aliases de contato
    try:
        aliases = storage.list_aliases_for_contact(owner, "+5511988887777")
        ok = len(aliases) > 0
        test_result("Listar aliases de contato", ok, f"Aliases: {aliases}")
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    except Exception as e:
        test_result("Listar aliases de contato", False, str(e))
        failed += 1

    # ========== RESUMO ==========
    print("\n" + "=" * 60)
    total = passed + failed
    pct = (passed / total * 100) if total > 0 else 0
    print(f"  RESULTADO: {passed}/{total} testes passaram ({pct:.0f}%)")
    if failed > 0:
        print(f"  {RED}{failed} testes falharam{RESET}")
    else:
        print(f"  {GREEN}Todos os testes passaram!{RESET}")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
