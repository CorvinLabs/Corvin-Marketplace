import type { AppProps } from 'next/app';
import Head from 'next/head';
import '@/styles/globals.css';

export default function App({ Component, pageProps }: AppProps) {
  return (
    <>
      <Head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="description" content="Corvin Marketplace - Discover and install plugins for CorvinOS" />
        <meta property="og:title" content="Corvin Marketplace" />
        <meta property="og:description" content="Discover and install plugins for CorvinOS" />
        <meta property="og:type" content="website" />
        <title>Corvin Marketplace - Plugins for CorvinOS</title>
      </Head>
      <Component {...pageProps} />
    </>
  );
}
