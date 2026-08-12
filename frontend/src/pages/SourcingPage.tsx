/** Task 2 placeholder — the route exists so the shape of the product is visible. */
export default function SourcingPage() {
  return (
    <>
      <h1>Find candidates</h1>
      <p className="subtitle">
        Describe a role, search for people who match, and have the assistant reach out —
        with their answers landing on the same results dashboard.
      </p>

      <div className="panel">
        <h2>Coming soon</h2>
        <p className="muted doc">Here's how it will work:</p>
        <ol className="muted doc">
          <li>Paste a job description.</li>
          <li>See a list of people whose experience matches it.</li>
          <li>Pick the ones worth approaching.</li>
          <li>The assistant calls them and asks your screening questions.</li>
          <li>Their answers appear under Results, alongside everyone else's.</li>
        </ol>

        <h3>How we'll handle it responsibly</h3>
        <p className="muted doc">
          People found through a search have not asked to be contacted, so this part will
          start in practice mode, and reaching out will always be something you choose
          person by person — never a bulk action that runs on its own.
        </p>
      </div>
    </>
  );
}
