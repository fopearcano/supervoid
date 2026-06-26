import { useEffect, useState } from 'react';
import { listCatalogue } from '../api/reader';
import type { CatalogueItem } from '../types/reader';
import { Wordmark } from '../components/Wordmark';
import { CoverImage } from '../components/CoverImage';
import { Spinner } from '../components/Spinner';
import { Link, readerPaths } from '../router';

const CURRENCY_SYMBOLS: Record<string, string> = { EUR: '€', USD: '$', GBP: '£' };

function formatPrice(cents: number | null, currency: string): string | null {
  if (cents == null) return null;
  const amount = (cents / 100).toFixed(2);
  const symbol = CURRENCY_SYMBOLS[currency];
  return symbol ? `${symbol}${amount}` : `${amount} ${currency}`;
}

function CatalogueCard({ item }: { item: CatalogueItem }) {
  const price = formatPrice(item.price_cents, item.currency);
  return (
    <div className="group flex flex-col">
      <Link
        to={readerPaths.work(item.slug)}
        className="relative aspect-[2/3] overflow-hidden border border-rule bg-ink-700"
        aria-label={`View ${item.title}`}
      >
        <CoverImage
          src={item.cover_image}
          alt={item.title}
          className="transition-transform duration-700 group-hover:scale-[1.03]"
        />
      </Link>

      <h3 className="mt-4 font-serif text-xl leading-tight text-parchment">
        {item.title}
      </h3>
      {item.subtitle && (
        <p className="mt-1 font-serif text-sm italic text-parchment-dim">
          {item.subtitle}
        </p>
      )}
      {item.author_credit && (
        <p className="mt-1 font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">
          {item.author_credit}
        </p>
      )}
      {item.public_synopsis && (
        <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-parchment-muted/80">
          {item.public_synopsis}
        </p>
      )}
      {item.format_label && (
        <p className="mt-2 font-mono text-[0.54rem] uppercase tracking-widest text-parchment-shadow">
          {item.format_label}
        </p>
      )}

      <div className="mt-3 flex items-center justify-between gap-3 border-t border-rule pt-3">
        <span className="font-serif text-lg text-parchment">{price ?? '—'}</span>
        {item.buy_url ? (
          <a href={item.buy_url} target="_blank" rel="noreferrer" className="button-accent">
            Buy ↗
          </a>
        ) : (
          <span className="font-mono text-[0.6rem] uppercase tracking-widest text-parchment-dim">
            Coming soon
          </span>
        )}
      </div>
    </div>
  );
}

/** The public Bookshop — SUPERVOID's selling catalogue. */
export function ShopPage() {
  const [items, setItems] = useState<CatalogueItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    listCatalogue()
      .then((data) => active && setItems(data))
      .catch((err) => active && setError(err?.message ?? String(err)));
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="sv-reader-root flex min-h-screen flex-col text-parchment">
      <header className="border-b border-rule">
        <div className="mx-auto flex w-full max-w-editorial items-center justify-between px-6 py-5">
          <Wordmark subtitle="Bookshop" />
          <a
            href="/"
            className="font-mono text-[0.56rem] uppercase tracking-[0.28em] text-parchment-shadow transition-colors hover:text-parchment"
          >
            ← Home
          </a>
        </div>
      </header>

      <main className="mx-auto w-full max-w-editorial flex-1 px-6 py-12">
        <div className="border-b border-rule pb-10">
          <p className="label-eyebrow">Bookshop</p>
          <h1 className="mt-4 max-w-2xl font-serif text-5xl leading-[1.05] text-parchment">
            The SUPERVOID Catalogue
          </h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-parchment-muted/80">
            Editions published by SUPERVOID, available to buy. Each links out to
            its point of sale.
          </p>
        </div>

        <div className="mt-12">
          {error && (
            <p className="font-mono text-sm text-signal">
              Could not load the catalogue — {error}
            </p>
          )}
          {!items && !error && <Spinner label="Loading catalogue" />}
          {items && items.length === 0 && (
            <p className="font-serif text-lg italic text-parchment-dim">
              Nothing for sale yet.
            </p>
          )}
          {items && items.length > 0 && (
            <div className="grid grid-cols-2 gap-x-8 gap-y-12 sm:grid-cols-3 lg:grid-cols-4">
              {items.map((item) => (
                <CatalogueCard key={item.id} item={item} />
              ))}
            </div>
          )}
        </div>
      </main>

      <footer className="border-t border-rule">
        <div className="mx-auto w-full max-w-editorial px-6 py-8">
          <p className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-shadow">
            SUPERVOID ENTANGLED · Publishing — bookshop
          </p>
        </div>
      </footer>
    </div>
  );
}
