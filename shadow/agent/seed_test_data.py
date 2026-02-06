"""
Seed script para popular o Shadow com dados de teste.
Uso: python seed_test_data.py
"""

import os
import sys
from datetime import datetime, timedelta

# Adiciona o diretório ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage import Storage


def seed_database():
    """Popula o banco com dados de teste."""
    storage = Storage()
    owner = os.getenv("SHADOW_OWNER_E164", "+5511999999999")

    print(f"🌱 Iniciando seed para owner: {owner}")

    # ========== CONTATOS ==========
    contacts = [
        ("+5511988887777", "João Silva"),
        ("+5511977776666", "Maria Santos"),
        ("+5511966665555", "Carlos Oliveira"),
        ("+5511955554444", "Ana Costa"),
        ("+5511944443333", "Pedro Souza"),
    ]

    print("\n📇 Criando contatos...")
    for phone, name in contacts:
        storage.upsert_contact(phone, name)
        storage.update_contact_context(owner, phone, name)
        print(f"   ✓ {name} ({phone})")

    # ========== ALIASES ==========
    aliases = [
        ("+5511988887777", "joao"),
        ("+5511988887777", "joaozinho"),
        ("+5511977776666", "maria"),
        ("+5511966665555", "carlos"),
        ("+5511966665555", "carlinhos"),
    ]

    print("\n🏷️  Criando aliases...")
    for phone, alias in aliases:
        storage.add_contact_alias(owner, phone, alias)
        print(f"   ✓ {alias} → {phone[-4:]}")

    # ========== TAREFAS ==========
    now = datetime.now()
    tasks_data = [
        ("Ligar para João sobre o contrato", now + timedelta(hours=2)),
        ("Enviar proposta para Maria", now + timedelta(days=1)),
        ("Revisar relatório do Carlos", now + timedelta(days=2)),
        ("Agendar reunião com Ana", now + timedelta(days=3)),
        ("Cobrar pagamento do Pedro", now + timedelta(days=7)),
    ]

    print("\n📋 Criando tarefas...")
    for title, due in tasks_data:
        task = storage.create_task(title, due.isoformat())
        print(f"   ✓ [{task.id}] {title}")

    # ========== COMPROMISSOS ==========
    appointments_data = [
        ("Reunião com João - Contrato", now + timedelta(days=1, hours=10)),
        ("Call com Maria - Proposta", now + timedelta(days=2, hours=14)),
        ("Almoço com Carlos", now + timedelta(days=3, hours=12)),
    ]

    print("\n📅 Criando compromissos...")
    for title, scheduled in appointments_data:
        appt = storage.create_appointment(title, scheduled.isoformat(), 60)
        print(f"   ✓ [{appt.id}] {title}")

    # ========== LEMBRETES ==========
    reminders_data = [
        (now + timedelta(hours=1), "Lembrar de ligar para João"),
        (now + timedelta(days=1, hours=9), "Preparar proposta para Maria"),
        (now + timedelta(days=2, hours=13), "Call com Maria em 1 hora"),
    ]

    print("\n⏰ Criando lembretes...")
    for remind_at, message in reminders_data:
        storage.create_reminder(remind_at.isoformat(), message, target_phone=owner)
        print(f"   ✓ {message}")

    # ========== MENSAGENS DE TESTE ==========
    messages = [
        ("+5511988887777", "João Silva", "Oi, preciso falar sobre o contrato"),
        ("+5511988887777", "João Silva", "Pode ser amanhã às 10h?"),
        ("+5511977776666", "Maria Santos", "Bom dia! A proposta está pronta?"),
        ("+5511977776666", "Maria Santos", "Prefiro receber por email"),
        ("+5511966665555", "Carlos Oliveira", "O relatório precisa de revisão"),
    ]

    print("\n💬 Criando mensagens...")
    for phone, name, content in messages:
        storage.ingest_message(
            chat_id=f"{phone}@s.whatsapp.net",
            chat_type="direct",
            sender=phone,
            sender_name=name,
            content=content,
            direction="inbound",
            is_owner=False,
        )
        print(f"   ✓ [{name}]: {content[:30]}...")

    # ========== ENTIDADES EXTRAÍDAS ==========
    entities = [
        (
            "task",
            {
                "description": "Enviar contrato para João",
                "due_date": (now + timedelta(days=1)).isoformat(),
                "assigned_to": "João",
            },
        ),
        (
            "task",
            {
                "description": "Preparar apresentação",
                "due_date": (now + timedelta(days=3)).isoformat(),
            },
        ),
        (
            "meeting",
            {
                "title": "Reunião de projeto",
                "date": (now + timedelta(days=2)).isoformat(),
                "participants": ["João", "Maria"],
            },
        ),
    ]

    print("\n🔍 Criando entidades extraídas...")
    for entity_type, data in entities:
        storage.save_extracted_entity(
            owner_id=owner,
            source_chat_id="+5511988887777@s.whatsapp.net",
            source_message_id=None,
            entity_type=entity_type,
            entity_data=data,
            confidence=0.85,
        )
        print(f"   ✓ {entity_type}: {data.get('description') or data.get('title')}")

    # ========== MEMÓRIAS DE CONTATO ==========
    memories = [
        ("+5511988887777", "João prefere reuniões pela manhã", "preference", 0.8),
        ("+5511977776666", "Maria trabalha na área de vendas", "fact", 0.7),
        ("+5511977776666", "Maria prefere receber documentos por email", "preference", 0.9),
        ("+5511966665555", "Carlos é responsável pelos relatórios mensais", "fact", 0.8),
    ]

    print("\n🧠 Criando memórias...")
    for phone, text, category, importance in memories:
        storage.save_contact_memory(
            owner_id=owner,
            text=text,
            contact_phone=phone,
            category=category,
            importance=importance,
        )
        print(f"   ✓ [{category}] {text[:40]}...")

    # ========== TASK-CONTACT LINKS ==========
    print("\n🔗 Vinculando tarefas a contatos...")
    storage.link_task_to_contact(1, "+5511988887777", "João Silva", "assigned")
    storage.link_task_to_contact(2, "+5511977776666", "Maria Santos", "requester")
    print("   ✓ Tarefa 1 → João (assigned)")
    print("   ✓ Tarefa 2 → Maria (requester)")

    print("\n" + "=" * 50)
    print("✅ Seed completo!")
    print("=" * 50)
    print(f"   - {len(contacts)} contatos")
    print(f"   - {len(aliases)} aliases")
    print(f"   - {len(tasks_data)} tarefas")
    print(f"   - {len(appointments_data)} compromissos")
    print(f"   - {len(reminders_data)} lembretes")
    print(f"   - {len(messages)} mensagens")
    print(f"   - {len(entities)} entidades")
    print(f"   - {len(memories)} memórias")


if __name__ == "__main__":
    seed_database()
