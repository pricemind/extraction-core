from abc import abstractmethod

import jmespath


class ITransformer:
    @abstractmethod
    def transform(self, data: dict) -> dict:
        raise NotImplementedError('transform method must be implemented')


class DummyTransformer(ITransformer):
    def transform(self, data: dict):
        return data


class MagentoTransformer(ITransformer):
    def transform(self, data: dict) -> list[dict]:
        if not data:
            return []
        fields = jmespath.search(
            '"[data-role=swatch-options]"."Magento_Swatches/js/swatch-renderer".jsonConfig.{sku: sku, optionPrices: optionPrices,images: images}',
            data)
        merged = {}
        # We merge by first keys only
        if fields:
            i = 0
            for obj in fields:
                i += 1
                # Check if fields[obj] is iterrable
                if not isinstance(fields[obj], dict):
                    continue
                for key in fields[obj]:
                    if key not in merged and i == 1:
                        merged[key] = {}
                    try:
                        merged[key][obj] = fields[obj][key]
                    except KeyError:
                        pass
        # Process attributes

        index = jmespath.search('"[data-role=swatch-options]"."Magento_Swatches/js/swatch-renderer".jsonConfig.index',
                                data)
        attributes = jmespath.search(
            '"[data-role=swatch-options]"."Magento_Swatches/js/swatch-renderer".jsonConfig.attributes', data)

        for pid, vals in index.items():
            # get attribute value
            for k, v in vals.items():
                if k in attributes and 'options' in attributes[k] and isinstance(attributes[k]['options'], list):
                    if pid not in merged:
                        merged[pid] = {}
                    if 'attributes' in merged[pid]:
                        merged[pid]['attributes'] += ', ' + attributes[k]['label'] + ": " + next(
                            o['label'] for o in attributes[k]['options'] if o['id'] == v)
                    else:
                        merged[pid]['attributes'] = attributes[k]['label'] + ': ' + next(
                            o['label'] for o in attributes[k]['options'] if o['id'] == v)

        return list(merged.values())
