-- Dados de demonstração do Portal de Solicitações (card BD-02).
-- Idempotente: pode ser executado várias vezes sem duplicar registros.
-- Gerado por script; as senhas são só de demonstração e estão no README.
--
-- Uso:  python manage.py carregar_seed        (dentro de backend/)
--   ou: psql "$DATABASE_URL" -f database/seed.sql

-- Categorias (D07)
INSERT INTO categorias (nome, ativa) VALUES
  ('TI', true),
  ('RH', true),
  ('Compras', true),
  ('Financeiro', true),
  ('Infraestrutura', true)
ON CONFLICT (nome) DO NOTHING;

-- Usuários (D01, D08). Senhas em PBKDF2-SHA256, o formato do Django.
INSERT INTO usuarios (login, nome, senha_hash, papel, ativo, administrador) VALUES
  ('maria.solicitante', 'Maria Souza', 'pbkdf2_sha256$1000000$demoMaria0001$s15bb5jAsdK76846uWNXubSo/t98OVhWeZqUH3XZwcE=', 'SOLICITANTE', true, false),
  ('joao.solicitante', 'João Lima', 'pbkdf2_sha256$1000000$demoJoao00002$25vmOjer4OYS8osdAZmYqOs26oD3Jm4Ge8wcXZglyzQ=', 'SOLICITANTE', true, false),
  ('ana.atendente', 'Ana Ribeiro', 'pbkdf2_sha256$1000000$demoAna000003$Hbq9teZpESWhUN0UtD9GdMZ+GOEp8Y4Knxsnr22sS7A=', 'ATENDENTE', true, false),
  ('admin', 'Administrador', 'pbkdf2_sha256$1000000$demoAdmin0004$xOoHs7PKWPcYvwK6JY678AQQSQ47GzypxUtSYDPs9cM=', 'SOLICITANTE', true, true)
ON CONFLICT (login) DO NOTHING;

-- Solicitações em status variados, para o dashboard não abrir zerado
INSERT INTO solicitacoes
  (id, titulo, descricao, categoria_id, solicitante_id, status, criado_em, atualizado_em)
SELECT v.id, v.titulo, v.descricao, c.id, u.id, v.status, v.criado_em::timestamptz, v.atualizado_em::timestamptz
FROM (VALUES
  (1, 'Notebook não liga após atualização', 'O notebook da mesa 14 não liga depois da atualização de ontem. A luz de energia pisca e a tela fica apagada.', 'TI', 'maria.solicitante', 'CONCLUIDO', '2026-09-21 09:10-03', '2026-09-22 15:45-03'),
  (2, 'Segunda via do holerite de agosto', 'Preciso da segunda via do holerite de agosto para apresentar na renovação do contrato de aluguel.', 'RH', 'joao.solicitante', 'CONCLUIDO', '2026-09-22 11:05-03', '2026-09-23 09:30-03'),
  (3, 'Compra de monitor adicional', 'Solicito a compra de um monitor de 24 polegadas para a estação de trabalho do time de atendimento.', 'Compras', 'maria.solicitante', 'CONCLUIDO', '2026-09-23 08:40-03', '2026-09-28 17:20-03'),
  (4, 'Troca de lâmpadas da sala 3', 'As duas lâmpadas do corredor da sala de reuniões 3 queimaram e o ambiente está escuro.', 'Infraestrutura', 'joao.solicitante', 'CONCLUIDO', '2026-09-24 13:25-03', '2026-09-25 11:10-03'),
  (5, 'Acesso à VPN para trabalho remoto', 'Preciso de acesso à VPN corporativa para trabalhar de casa às sextas-feiras, conforme acordado com a gestão.', 'TI', 'maria.solicitante', 'EM_ATENDIMENTO', '2026-09-25 09:50-03', '2026-09-28 09:20-03'),
  (6, 'Reembolso de despesas de viagem', 'Enviei as notas da viagem a São Paulo no dia 18 e ainda não recebi o reembolso das despesas.', 'Financeiro', 'joao.solicitante', 'EM_ATENDIMENTO', '2026-09-26 10:30-03', '2026-09-29 14:05-03'),
  (7, 'Atualização de dados bancários', 'Mudei de banco e preciso atualizar a conta onde recebo o salário antes do fechamento da folha.', 'RH', 'maria.solicitante', 'EM_ATENDIMENTO', '2026-09-28 16:15-03', '2026-09-29 08:50-03'),
  (8, 'Ar-condicionado pingando no financeiro', 'O ar-condicionado do setor financeiro está pingando água sobre duas mesas desde segunda-feira.', 'Infraestrutura', 'joao.solicitante', 'EM_ATENDIMENTO', '2026-09-29 11:40-03', '2026-09-30 09:10-03'),
  (9, 'Instalação do pacote de design', 'Preciso do pacote de design instalado no meu computador para o projeto de comunicação interna.', 'TI', 'maria.solicitante', 'ABERTO', '2026-09-29 15:20-03', '2026-09-29 15:20-03'),
  (10, 'Cotação de cadeiras ergonômicas', 'Solicito cotação de cinco cadeiras ergonômicas para a equipe que trabalha mais de seis horas sentada.', 'Compras', 'joao.solicitante', 'ABERTO', '2026-09-30 10:05-03', '2026-09-30 10:05-03'),
  (11, 'Dúvida sobre desconto no contracheque', 'Apareceu um desconto de plano de saúde que não reconheço no contracheque deste mês.', 'Financeiro', 'maria.solicitante', 'ABERTO', '2026-09-30 17:35-03', '2026-09-30 17:35-03'),
  (12, 'Declaração de vínculo empregatício', 'Preciso de uma declaração de vínculo empregatício para apresentar no banco até a próxima semana.', 'RH', 'joao.solicitante', 'ABERTO', '2026-10-01 08:45-03', '2026-10-01 08:45-03')
) AS v(id, titulo, descricao, categoria, solicitante, status, criado_em, atualizado_em)
JOIN categorias c ON c.nome = v.categoria
JOIN usuarios u ON u.login = v.solicitante
ON CONFLICT (id) DO NOTHING;

-- O seed usa ids fixos; ajusta a sequência para os próximos ids não colidirem
SELECT setval(pg_get_serial_sequence('solicitacoes', 'id'), (SELECT MAX(id) FROM solicitacoes));

-- Histórico (D11): a criação e cada mudança de status, na ordem em que ocorreram
INSERT INTO historico_status (solicitacao_id, status_anterior, status_novo, alterado_por_id, alterado_em)
SELECT v.solicitacao_id, v.status_anterior, v.status_novo, u.id, v.alterado_em::timestamptz
FROM (VALUES
  (1, NULL::varchar, 'ABERTO', 'maria.solicitante', '2026-09-21 09:10-03'),
  (1, 'ABERTO', 'EM_ATENDIMENTO', 'ana.atendente', '2026-09-21 10:30-03'),
  (1, 'EM_ATENDIMENTO', 'CONCLUIDO', 'ana.atendente', '2026-09-22 15:45-03'),
  (2, NULL::varchar, 'ABERTO', 'joao.solicitante', '2026-09-22 11:05-03'),
  (2, 'ABERTO', 'EM_ATENDIMENTO', 'ana.atendente', '2026-09-22 14:00-03'),
  (2, 'EM_ATENDIMENTO', 'CONCLUIDO', 'ana.atendente', '2026-09-23 09:30-03'),
  (3, NULL::varchar, 'ABERTO', 'maria.solicitante', '2026-09-23 08:40-03'),
  (3, 'ABERTO', 'EM_ATENDIMENTO', 'ana.atendente', '2026-09-24 10:15-03'),
  (3, 'EM_ATENDIMENTO', 'CONCLUIDO', 'ana.atendente', '2026-09-28 17:20-03'),
  (4, NULL::varchar, 'ABERTO', 'joao.solicitante', '2026-09-24 13:25-03'),
  (4, 'ABERTO', 'EM_ATENDIMENTO', 'ana.atendente', '2026-09-24 15:00-03'),
  (4, 'EM_ATENDIMENTO', 'CONCLUIDO', 'ana.atendente', '2026-09-25 11:10-03'),
  (5, NULL::varchar, 'ABERTO', 'maria.solicitante', '2026-09-25 09:50-03'),
  (5, 'ABERTO', 'EM_ATENDIMENTO', 'ana.atendente', '2026-09-28 09:20-03'),
  (6, NULL::varchar, 'ABERTO', 'joao.solicitante', '2026-09-26 10:30-03'),
  (6, 'ABERTO', 'EM_ATENDIMENTO', 'ana.atendente', '2026-09-29 14:05-03'),
  (7, NULL::varchar, 'ABERTO', 'maria.solicitante', '2026-09-28 16:15-03'),
  (7, 'ABERTO', 'EM_ATENDIMENTO', 'ana.atendente', '2026-09-29 08:50-03'),
  (8, NULL::varchar, 'ABERTO', 'joao.solicitante', '2026-09-29 11:40-03'),
  (8, 'ABERTO', 'EM_ATENDIMENTO', 'ana.atendente', '2026-09-30 09:10-03'),
  (9, NULL::varchar, 'ABERTO', 'maria.solicitante', '2026-09-29 15:20-03'),
  (10, NULL::varchar, 'ABERTO', 'joao.solicitante', '2026-09-30 10:05-03'),
  (11, NULL::varchar, 'ABERTO', 'maria.solicitante', '2026-09-30 17:35-03'),
  (12, NULL::varchar, 'ABERTO', 'joao.solicitante', '2026-10-01 08:45-03')
) AS v(solicitacao_id, status_anterior, status_novo, login, alterado_em)
JOIN usuarios u ON u.login = v.login
JOIN solicitacoes s ON s.id = v.solicitacao_id
WHERE NOT EXISTS (
  SELECT 1 FROM historico_status h
  WHERE h.solicitacao_id = v.solicitacao_id AND h.status_novo = v.status_novo
);
