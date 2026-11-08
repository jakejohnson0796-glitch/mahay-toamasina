"""Agent STT uniquement pour les cours Mahay.

L'agent ne répond pas, ne diffuse pas de voix et ne lance aucune capture vidéo.
Il publie les segments transcrits dans le flux LiveKit lk.transcription.
"""
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli
from livekit.plugins import groq

server = AgentServer()


@server.rtc_session(agent_name="mahay-transcription")
async def transcrire_cours(ctx: JobContext) -> None:
    session = AgentSession(
        stt=groq.STT(model="whisper-large-v3-turbo", language="fr"),
        record=False,
    )
    await session.start(
        agent=Agent(
            instructions=(
                "Tu es un moteur de transcription seulement. Tu n'engages aucune conversation, "
                "tu ne réponds pas aux participants, tu n'émets aucune voix et tu ne produis "
                "aucune analyse. Transcris fidèlement la parole en français."
            )
        ),
        room=ctx.room,
    )
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)
