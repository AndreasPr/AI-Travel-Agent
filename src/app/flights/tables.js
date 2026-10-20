export default function PredictionResultTable({results, recommendation}) {

    if (!results) return <div></div>
    if (results.length === 0) return <div></div>

    const firstResult = results[0]
    const colNames = Object.keys(firstResult)

    const priceColIdx = colNames.map(x => x.toLocaleLowerCase()).indexOf('price')
    const dateColIdx = colNames.map(x => x.toLocaleLowerCase()).indexOf('date')
    const requestIdColIdx = colNames.map(x => x.toLocaleLowerCase()).indexOf('requestid')

    return <div className="relative overflow-x-auto shadow-md sm:rounded-lg">
        <table className="w-full text-sm text-left rtl:text-right text-blue-100 dark:text-blue-100">
            <thead className="text-xs text-white uppercase bg-blue-600 border-b border-blue-400 dark:text-white">
                <tr>
                    {colNames.map((col, idx) => {
                        if (requestIdColIdx === idx){
                            return <th scope="col" key={idx} className="px-6 py-3"></th>
                        }
                        return <th scope="col" key={idx} className="px-6 py-3">{col}</th>
                    })}
                </tr>
            </thead>
            <tbody>
                {results.map((pred, trIdx) => {
                    const trValues = Object.values(pred)
                    let className = "bg-blue-600 border-b border-blue-400 hover:bg-blue-500"
                    const isRecommended = pred.requestID === recommendation.requestID
                    if (isRecommended){
                        className = "bg-red-600 text-black font-bold border-b border-red-400 hover:bg-red-500"
                    }

                    return <tr key={trIdx} className={className}>
                        {trValues && trValues.map((trCol, tcolIdx) => {
                            if (tcolIdx === requestIdColIdx){
                                const recLabel = isRecommended ? "->" : ""
                                return <td key={`${trIdx}-${tcolIdx}`} className="px-6 py-4">{recLabel}</td>
                            }
                            const isDateCol = dateColIdx === tcolIdx
                            const isPriceCol = priceColIdx === tcolIdx
                            const renderedDate = isDateCol ? new Date(Date.parse(trCol)).toLocaleDateString() : null
                            const renderedPrice = isPriceCol ? new Intl.NumberFormat('en-US', {style: "currency", currency: "USD"}).format(trCol) : null
                            const isOne = trCol === 1
                            const yesVal = isOne ? "Yes": null
                            const isZero = trCol === 0
                            const noVal = isZero ? "No" : null
                            const rendetedCol = renderedDate ? renderedDate : renderedPrice ? renderedPrice : yesVal ? yesVal : noVal ? noVal : trCol
                            return <td key={`${trIdx}-${tcolIdx}`} className="px-6 py-4">{rendetedCol}</td>
                        })}
                    </tr>
                })}
            </tbody>
        </table>
    </div>
}
