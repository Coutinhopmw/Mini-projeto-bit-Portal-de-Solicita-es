import { useEffect, useState } from 'react'

export default function App() {
  const [mensagem, setMensagem] = useState('Carregando...')

  useEffect(() => {
    fetch('/api/ola/')
      .then((resposta) => resposta.json())
      .then((dados) => setMensagem(dados.mensagem))
      .catch(() => setMensagem('Olá, mundo! (API fora do ar)'))
  }, [])

  return (
    <main>
      <h1>Portal de Solicitações</h1>
      <p>{mensagem}</p>
    </main>
  )
}
