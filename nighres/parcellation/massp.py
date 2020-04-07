import numpy as np
import nibabel as nb
import os
import sys
import nighresjava
from ..io import load_volume, save_volume
from ..utils import _output_dir_4saving, _fname_4saving, \
                    _check_topology_lut_dir, _check_available_memory
from nighres.global_settings import DEFAULT_MASSP_ATLAS, DEFAULT_MASSP_HIST, \
                    DEFAULT_MASSP_SPATIAL_PROBA, DEFAULT_MASSP_SPATIAL_LABEL, \
                    DEFAULT_MASSP_SKEL_PROBA, DEFAULT_MASSP_SKEL_LABEL
from nighres.data.download_data import download_MASSP_atlas


def massp(target_images, structures, contrasts,
                      shape_atlas_probas=None, shape_atlas_labels=None, 
                      intensity_atlas_hist=None,
                      skeleton_atlas_probas=None, skeleton_atlas_labels=None, 
                      map_to_target=None,
                      max_iterations=80, max_difference=0.1,
                      save_data=False, overwrite=False, output_dir=None,
                      file_name=None):
    """ Multi-contrast Anatomical Subcortical Structure parcellation (MASSP)

    Estimates subcortical structures based on a multi-atlas approach on shape

    Parameters
    ----------
    target_images: [niimg]
        Input images to perform the parcellation from
    structures: int
        Number of structures to parcellate
    contrasts: int
       Number of image intensity contrasts
    shape_atlas_probas: niimg (opt)
        Pre-computed shape atlas probabilities (default is loaded from nighres atlas)
    shape_atlas_labels: niimg (opt)
        Pre-computed shape atlas labels (default is loaded from nighres atlas)
    intensity_atlas_hist: niimg (opt)
        Pre-computed intensity atlas from the contrast images  (default is loaded from nighres atlas)
    skeleton_atlas_probas: niimg (opt)
        Pre-computed skeleton atlas probabilities (default is loaded from nighres atlas)
    skeleton_atlas_labels: niimg (opt)
        Pre-computed skeleton atlas labels (default is loaded from nighres atlas)
    map_to_target: niimg
        Coordinate mapping from the atlas to the target (opt)
    max_iterations: int
        Maximum number of diffusion iterations to perform
    max_difference: float
        Maximum difference between diffusion steps
    save_data: bool
        Save output data to file (default is False)
    overwrite: bool
        Overwrite existing results (default is False)
    output_dir: str, optional
        Path to desired output directory, will be created if it doesn't exist
    file_name: str, optional
        Desired base name for output files with file extension
        (suffixes will be added)

    Returns
    ----------
    dict
        Dictionary collecting outputs under the following keys
        (suffix of output files in brackets)

        * max_proba (niimg): Maximum probability map (_massp-proba)
        * max_label (niimg): Maximum probability labels (_massp-label)

    Notes
    ----------
    Original Java module by Pierre-Louis Bazin.
    """

    print('\nMASSP')

    # check topology_lut_dir and set default if not given
    topology_lut_dir = _check_topology_lut_dir(None)

    # make sure that saving related parameters are correct
    if save_data:
        output_dir = _output_dir_4saving(output_dir, target_images[0])

        proba_file = os.path.join(output_dir, 
                        _fname_4saving(module=__name__,file_name=file_name,
                                  rootfile=target_images[0],
                                  suffix='massp-proba', ))

        label_file = os.path.join(output_dir, 
                        _fname_4saving(module=__name__,file_name=file_name,
                                   rootfile=target_images[0],
                                   suffix='massp-label'))

        if overwrite is False \
            and os.path.isfile(proba_file) \
            and os.path.isfile(label_file):
            
            print("skip computation (use existing results)")
            output = {'max_proba': proba_file, 
                      'max_label': label_file}
            return output


    # start virtual machine, if not already running
    try:
        mem = _check_available_memory()
        nighresjava.initVM(initialheap=mem['init'], maxheap=mem['max'])
    except ValueError:
        pass
    # create instance
    massp = nighresjava.ConditionalShapeSegmentation()

    # set parameters
    massp.setNumberOfSubjectsObjectsAndContrasts(1,structures,contrasts)
    massp.setOptions(True, False, False, False, True)
    massp.setDiffusionParameters(max_iterations, max_difference)
    
    # load target image for parameters
    print("load: "+str(target_images[0]))
    img = load_volume(target_images[0])
    data = img.get_data()
    trg_affine = img.get_affine()
    trg_header = img.get_header()
    trg_resolution = [x.item() for x in trg_header.get_zooms()]
    trg_dimensions = data.shape

    massp.setTargetDimensions(trg_dimensions[0], trg_dimensions[1], trg_dimensions[2])
    massp.setTargetResolutions(trg_resolution[0], trg_resolution[1], trg_resolution[2])

    # target image 1
    massp.setTargetImageAt(0, nighresjava.JArray('float')(
                                            (data.flatten('F')).astype(float)))
    
    # if further contrast are specified, input them
    for contrast in range(1,contrasts):    
        print("load: "+str(target_images[contrast]))
        data = load_volume(target_images[contrast]).get_data()
        massp.setTargetImageAt(contrast, nighresjava.JArray('float')(
                                            (data.flatten('F')).astype(float)))

    # if not specified, check if standard atlases are available or download them
    if ( (intensity_atlas_hist is None) or (shape_atlas_probas is None) or (shape_atlas_labels is None)
        or (skeleton_atlas_probas is None) or (skeleton_atlas_labels is None)):
        
        if (not os.path.exists(DEFAULT_MASSP_ATLAS)):
            download_MASSP_atlas(overwrite=False)
            
        intensity_atlas_hist = DEFAULT_MASSP_HIST
        shape_atlas_probas = DEFAULT_MASSP_SPATIAL_PROBA
        shape_atlas_labels = DEFAULT_MASSP_SPATIAL_LABEL
        skeleton_atlas_probas = DEFAULT_MASSP_SKEL_PROBA
        skeleton_atlas_labels = DEFAULT_MASSP_SKEL_LABEL
        

    # load the shape and intensity atlases
    print("load: "+str(intensity_atlas_hist))
    hist = load_volume(intensity_atlas_hist).get_data()
    massp.setConditionalHistogram(nighresjava.JArray('float')(
                                        (hist.flatten('F')).astype(float)))

    print("load: "+str(shape_atlas_probas))
    
    # load a first image for dim, res
    img = load_volume(shape_atlas_probas)
    pdata = img.get_data()
    header = img.get_header()
    affine = img.get_affine()
    resolution = [x.item() for x in header.get_zooms()]
    dimensions = pdata.shape
    
    massp.setAtlasDimensions(dimensions[0], dimensions[1], dimensions[2])
    massp.setAtlasResolutions(resolution[0], resolution[1], resolution[2])

    print("load: "+str(shape_atlas_labels))
    ldata = load_volume(shape_atlas_labels).get_data()
    
    if map_to_target is not None:
        print("map atlas to subject")
        print("load: "+str(map_to_target))
        mdata =  load_volume(map_to_target).get_data()
        massp.setMappingToTarget(nighresjava.JArray('float')(
                                            (mdata.flatten('F')).astype(float)))
        
    massp.setShapeAtlasProbasAndLabels(nighresjava.JArray('float')(
                                (pdata.flatten('F')).astype(float)),
                                nighresjava.JArray('int')(
                                (ldata.flatten('F')).astype(int).tolist()))

    print("load: "+str(skeleton_atlas_probas))
    pdata = load_volume(skeleton_atlas_probas).get_data()
    
    print("load: "+str(skeleton_atlas_labels))
    ldata = load_volume(skeleton_atlas_labels).get_data()

    massp.setSkeletonAtlasProbasAndLabels(nighresjava.JArray('float')(
                                (pdata.flatten('F')).astype(float)),
                                nighresjava.JArray('int')(
                                (ldata.flatten('F')).astype(int).tolist()))

    # execute
    try:
        massp.estimateTarget()
        massp.fastSimilarityDiffusion(4)
        massp.collapseToJointMaps()
        massp.precomputeStoppingStatistics(3.0)
        massp.topologyBoundaryDefinition("wcs", topology_lut_dir)
        massp.conditionalPrecomputedDirectVolumeGrowth(3.0)
        massp.collapseSpatialPriorMaps()

    except:
        # if the Java module fails, reraise the error it throws
        print("\n The underlying Java code did not execute cleanly: ")
        print(sys.exc_info()[0])
        raise
        return

    # reshape output to what nibabel likes
    dims3Dtrg = (trg_dimensions[0],trg_dimensions[1],trg_dimensions[2])

    proba_data = np.reshape(np.array(massp.getFinalProba(),
                                    dtype=np.float32), dims3Dtrg, 'F')

    label_data = np.reshape(np.array(massp.getFinalLabel(),
                                    dtype=np.int32), dims3Dtrg, 'F')

    # adapt header max for each image so that correct max is displayed
    # and create nifiti objects
    trg_header['cal_max'] = np.nanmax(proba_data)
    proba = nb.Nifti1Image(proba_data, trg_affine, trg_header)

    trg_header['cal_max'] = np.nanmax(label_data)
    label = nb.Nifti1Image(label_data, trg_affine, trg_header)

    if save_data:
        save_volume(proba_file, proba)
        save_volume(label_file, label)

        output= {'max_proba': proba_file, 'max_label': label_file}
        return output
    else:
        output= {'max_proba': proba, 'max_label': label}
        return output


def massp_atlasing(subjects, structures, contrasts, 
                      levelset_images=None, skeleton_images=None, 
                      contrast_images=None, 
                      save_data=False, overwrite=False, output_dir=None,
                      file_name=None):
    """ MASSP Atlasing

    Builds a multi-atlas prior for MASSP

    Parameters
    ----------
    subjects: int
        Number of atlas subjects
    structures: int
        Number of structures to parcellate
    contrasts: int
       Number of image intensity contrasts
    levelset_images: [niimg]
        Atlas shape levelsets indexed by (subjects,structures)
    skeleton_images: [niimg]
        Atlas shape skeletons indexed by (subjects,structures)
    contrast_images: [niimg]
        Atlas images to use in the parcellation, indexed by (subjects, contrasts)
    save_data: bool
        Save output data to file (default is False)
    overwrite: bool
        Overwrite existing results (default is False)
    output_dir: str, optional
        Path to desired output directory, will be created if it doesn't exist
    file_name: str, optional
        Desired base name for output files with file extension
        (suffixes will be added)

    Returns
    ----------
    dict
        Dictionary collecting outputs under the following keys
        (suffix of output files in brackets)

        * max_spatial_proba (niimg): Maximum spatial probability map (_massp-sproba)
        * max_spatial_label (niimg): Maximum spatial probability labels (_massp-slabel)
        * cond_hist (niimg): Conditional intensity histograms (_massp-chist)
        * max_skeleton_proba (niimg): Maximum skeleton probability map (_massp-kproba)
        * max_skeleton_label (niimg): Maximum skeleton probability labels (_massp-klabel)

    Notes
    ----------
    Original Java module by Pierre-Louis Bazin.
    """

    print('\nMASSP Atlasing')

    # make sure that saving related parameters are correct
    if save_data:
        output_dir = _output_dir_4saving(output_dir, contrast_images[0][0])

        spatial_proba_file = os.path.join(output_dir, 
                        _fname_4saving(module=__name__,file_name=file_name,
                                  rootfile=contrast_images[0][0],
                                  suffix='massp-sproba', ))

        spatial_label_file = os.path.join(output_dir, 
                        _fname_4saving(module=__name__,file_name=file_name,
                                   rootfile=contrast_images[0][0],
                                   suffix='massp-slabel'))

        condhist_file = os.path.join(output_dir, 
                        _fname_4saving(module=__name__,file_name=file_name,
                                   rootfile=contrast_images[0][0],
                                   suffix='massp-chist'))
        
        skeleton_proba_file = os.path.join(output_dir, 
                        _fname_4saving(module=__name__,file_name=file_name,
                                  rootfile=contrast_images[0][0],
                                  suffix='massp-kproba', ))

        skeleton_label_file = os.path.join(output_dir, 
                        _fname_4saving(module=__name__,file_name=file_name,
                                   rootfile=contrast_images[0][0],
                                   suffix='massp-klabel'))

        
        if overwrite is False \
            and os.path.isfile(spatial_proba_file) \
            and os.path.isfile(spatial_label_file) \
            and os.path.isfile(condhist_file) \
            and os.path.isfile(skeleton_proba_file) \
            and os.path.isfile(skeleton_label_file):
            
            print("skip computation (use existing results)")
            output = {'max_spatial_proba': spatial_proba_file, 
                      'max_spatial_label': spatial_label_file,
                      'cond_hist': condhist_file,
                      'max_skeleton_proba': skeleton_proba_file, 
                      'max_skeleton_label': skeleton_label_file}

            return output


    # start virtual machine, if not already running
    try:
        mem = _check_available_memory()
        nighresjava.initVM(initialheap=mem['init'], maxheap=mem['max'])
    except ValueError:
        pass
    # create instance
    massp = nighresjava.ConditionalShapeSegmentation()

    # set parameters
    massp.setNumberOfSubjectsObjectsAndContrasts(subjects,structures,contrasts)
    massp.setOptions(True, False, False, False, True)
     
    # load target image for parameters
    # load a first image for dim, res
    img = load_volume(contrast_images[0][0])
    data = img.get_data()
    header = img.get_header()
    affine = img.get_affine()
    trg_resolution = [x.item() for x in header.get_zooms()]
    trg_dimensions = data.shape
    
    massp.setTargetDimensions(trg_dimensions[0], trg_dimensions[1], trg_dimensions[2])
    massp.setTargetResolutions(trg_resolution[0], trg_resolution[1], trg_resolution[2])

    resolution = trg_resolution
    dimensions = trg_dimensions
        
    massp.setAtlasDimensions(dimensions[0], dimensions[1], dimensions[2])
    massp.setAtlasResolutions(resolution[0], resolution[1], resolution[2])
    
    # load the atlas structures and contrasts, if needed
    for sub in range(subjects):
        for struct in range(structures):
            print("load: "+str(levelset_images[sub][struct]))
            data = load_volume(levelset_images[sub][struct]).get_data()
            massp.setLevelsetImageAt(sub, struct, nighresjava.JArray('float')(
                                                (data.flatten('F')).astype(float)))
        for contrast in range(contrasts):
            print("load: "+str(contrast_images[sub][contrast]))
            data = load_volume(contrast_images[sub][contrast]).get_data()
            massp.setContrastImageAt(sub, contrast, nighresjava.JArray('float')(
                                                (data.flatten('F')).astype(float)))
    # execute first step
    scale = 1.0
    try:
        scale = massp.computeAtlasPriors()
 
    except:
        # if the Java module fails, reraise the error it throws
        print("\n The underlying Java code did not execute cleanly: ")
        print(sys.exc_info()[0])
        raise
        return

    # clean up and go to second step
    levelset_images = None
    contrast_images = None
    
    for sub in range(subjects):
        for struct in range(structures):
            print("load: "+str(skeleton_images[sub][struct]))
            data = load_volume(skeleton_images[sub][struct]).get_data()
            massp.setSkeletonImageAt(sub, struct, nighresjava.JArray('float')(
                                                (data.flatten('F')).astype(float)))
                
    try:
        massp.computeSkeletonPriors(scale)
 
    except:
        # if the Java module fails, reraise the error it throws
        print("\n The underlying Java code did not execute cleanly: ")
        print(sys.exc_info()[0])
        raise
        return

    skeleton_images = None

    # reshape output to what nibabel likes
    dimensions = (dimensions[0],dimensions[1],dimensions[2],massp.getBestDimension())
    dimskel = (dimensions[0],dimensions[1],dimensions[2],int(massp.getBestDimension()/4))
    dims3Dtrg = (trg_dimensions[0],trg_dimensions[1],trg_dimensions[2])

    intens_dims = (structures+1,structures+1,contrasts)
    intens_hist_dims = ((structures+1)*(structures+1),massp.getNumberOfBins()+6,contrasts)

    spatial_proba_data = np.reshape(np.array(massp.getBestSpatialProbabilityMaps(dimensions[3]),
                                   dtype=np.float32), dimensions, 'F')

    spatial_label_data = np.reshape(np.array(massp.getBestSpatialProbabilityLabels(dimensions[3]),
                                    dtype=np.int32), dimensions, 'F')    

    intens_hist_data = np.reshape(np.array(massp.getConditionalHistogram(),
                                       dtype=np.float32), intens_hist_dims, 'F')

    skeleton_proba_data = np.reshape(np.array(massp.getBestSkeletonProbabilityMaps(dimskel[3]),
                                   dtype=np.float32), dimskel, 'F')

    skeleton_label_data = np.reshape(np.array(massp.getBestSkeletonProbabilityLabels(dimskel[3]),
                                    dtype=np.int32), dimskel, 'F')    


    # adapt header max for each image so that correct max is displayed
    # and create nifiti objects
    header['cal_max'] = np.nanmax(spatial_proba_data)
    spatial_proba = nb.Nifti1Image(spatial_proba_data, affine, header)

    header['cal_max'] = np.nanmax(spatial_label_data)
    spatial_label = nb.Nifti1Image(spatial_label_data, affine, header)

    chist = nb.Nifti1Image(intens_hist_data, None, None)

    header['cal_max'] = np.nanmax(skeleton_proba_data)
    skeleton_proba = nb.Nifti1Image(skeleton_proba_data, affine, header)

    header['cal_max'] = np.nanmax(skeleton_label_data)
    skeleton_label = nb.Nifti1Image(skeleton_label_data, affine, header)

    if save_data:
        save_volume(spatial_proba_file, spatial_proba)
        save_volume(spatial_label_file, spatial_label)
        save_volume(condhist_file, chist)
        save_volume(skeleton_proba_file, skeleton_proba)
        save_volume(skeleton_label_file, skeleton_label)
        output= {'max_spatial_proba': spatial_proba_file, 
                 'max_spatial_label': spatial_label_file, 
                 'cond_hist': condhist_file,
                 'max_skeleton_proba': skeleton_proba_file, 
                 'max_skeleton_label': skeleton_label_file}
        return output
    else:
        output= {'max_spatial_proba': spatial_proba, 
                 'max_spatial_label': spatial_label, 
                 'cond_hist': chist,
                 'max_skeleton_proba': skeleton_proba, 
                 'max_skeleton_label': skeleton_label}
        return output
