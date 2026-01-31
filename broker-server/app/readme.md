docker-compose up --build
docker-compose down -v 

DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO admin;
GRANT ALL ON SCHEMA public TO PUBLIC;

docker exec -it agent-database psql -U admin -d agent_db

alembic revision --autogenerate -m "initial"
alembic upgrade head

