import { render, screen } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import i18n from '../i18n'
import NotFound from './NotFound'

describe('NotFound', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('renders translated not found content and the home link', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <NotFound />
        </MemoryRouter>
      </I18nextProvider>,
    )

    expect(screen.getByRole('heading', { level: 1, name: i18n.t('notFound.title') })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: i18n.t('notFound.heading') })).toBeInTheDocument()
    expect(screen.getByText(i18n.t('notFound.message'))).toBeInTheDocument()

    expect(screen.getByRole('link', { name: i18n.t('notFound.backHome') })).toHaveAttribute('href', '/')
  })
})
